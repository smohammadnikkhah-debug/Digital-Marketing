require('dotenv').config();
const { createClient } = require('@supabase/supabase-js');
const readline = require('readline');

// Password Strength Validator
function validatePasswordStrength(password) {
  if (!password || typeof password !== 'string') {
    return { valid: false, message: 'Password is required.' };
  }
  if (password.length < 10) {
    return { valid: false, message: 'Password must be at least 10 characters long.' };
  }
  if (!/[A-Z]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one uppercase letter.' };
  }
  if (!/[a-z]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one lowercase letter.' };
  }
  if (!/[0-9]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one number.' };
  }
  if (!/[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?~`]/.test(password)) {
    return { valid: false, message: 'Password must contain at least one special character or symbol.' };
  }
  return { valid: true };
}

// Hidden / Masked Input Prompt (No plaintext echo in terminal, not in shell history)
function promptHidden(query) {
  return new Promise((resolve) => {
    process.stdout.write(query);

    if (process.stdin.isTTY) {
      process.stdin.setRawMode(true);
      process.stdin.resume();
      process.stdin.setEncoding('utf8');
      let input = '';

      const onData = (char) => {
        if (char === '\u0003') { // Ctrl+C
          process.stdout.write('\n');
          process.exit(1);
        } else if (char === '\r' || char === '\n') {
          process.stdin.setRawMode(false);
          process.stdin.pause();
          process.stdin.removeListener('data', onData);
          process.stdout.write('\n');
          resolve(input);
        } else if (char === '\u0008' || char === '\x7f') { // Backspace / Delete
          if (input.length > 0) {
            input = input.slice(0, -1);
            process.stdout.write('\b \b');
          }
        } else {
          input += char;
          process.stdout.write('*');
        }
      };

      process.stdin.on('data', onData);
    } else {
      // Non-interactive / piped fallback
      const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
        terminal: false
      });
      rl.question('', (answer) => {
        rl.close();
        resolve(answer.trim());
      });
    }
  });
}

async function runPasswordReset(targetIdentifier, options = {}) {
  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_KEY;

  if (!supabaseUrl || !supabaseKey) {
    console.error('❌ Error: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing from environment.');
    if (options.throwOnError) throw new Error('SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing');
    process.exit(1);
  }

  const supabase = createClient(supabaseUrl, supabaseKey);

  if (!targetIdentifier) {
    console.error('❌ Usage: npm run reset-admin-password -- <admin_username_or_email>');
    console.error('Example: npm run reset-admin-password -- info@mozarex.com');
    if (options.throwOnError) throw new Error('Target identifier required');
    process.exit(1);
  }

  const normalizedTarget = targetIdentifier.toLowerCase().trim();

  console.log('\n================================================================');
  console.log(' AIVEKAI ADMIN EMERGENCY PASSWORD RECOVERY                      ');
  console.log('================================================================');
  console.log(`Target Administrator: ${normalizedTarget}`);
  console.log('Verifying authoritative administrator authorization record...');

  // 1. Authoritative Authorization Check against public.aivekai_admin_users
  const { data: adminUsers, error: adminQueryErr } = await supabase
    .from('aivekai_admin_users')
    .select('id, auth_user_id, username, role, is_active');

  if (adminQueryErr) {
    console.error('❌ Database Query Error:', adminQueryErr.message);
    if (options.throwOnError) throw adminQueryErr;
    process.exit(1);
  }

  // Find target by username or match against auth users
  let matchedAdmin = (adminUsers || []).find(u => 
    u.username && u.username.toLowerCase() === normalizedTarget
  );

  // If not matched by username directly, resolve via Supabase Auth email lookup
  if (!matchedAdmin && normalizedTarget.includes('@')) {
    try {
      const { data: { users }, error: listErr } = await supabase.auth.admin.listUsers();
      if (!listErr && Array.isArray(users)) {
        const authUser = users.find(u => u.email && u.email.toLowerCase() === normalizedTarget);
        if (authUser) {
          matchedAdmin = (adminUsers || []).find(u => u.auth_user_id === authUser.id);
        }
      }
    } catch (authLookupErr) {
      // Ignore lookup error, fallback to unauthorized check
    }
  }

  if (!matchedAdmin) {
    console.error(`\n❌ Authorization Error: No authorized administrator account found matching "${normalizedTarget}".`);
    console.error('The recovery utility only resets existing authorized administrators and cannot create or elevate accounts.\n');
    if (options.throwOnError) throw new Error(`No authorized administrator account found matching "${normalizedTarget}"`);
    process.exit(1);
  }

  if (matchedAdmin.role !== 'admin') {
    console.error(`\n❌ Authorization Error: Account "${matchedAdmin.username}" does not have admin privileges (Role: ${matchedAdmin.role}).\n`);
    if (options.throwOnError) throw new Error(`Account "${matchedAdmin.username}" does not have admin privileges`);
    process.exit(1);
  }

  if (!matchedAdmin.is_active) {
    console.error(`\n❌ Authorization Error: Administrator account "${matchedAdmin.username}" is deactivated.\n`);
    if (options.throwOnError) throw new Error(`Administrator account "${matchedAdmin.username}" is deactivated`);
    process.exit(1);
  }

  if (!matchedAdmin.auth_user_id) {
    console.error(`\n❌ Error: Administrator account "${matchedAdmin.username}" is missing an associated auth_user_id.\n`);
    if (options.throwOnError) throw new Error(`Administrator account "${matchedAdmin.username}" is missing an associated auth_user_id`);
    process.exit(1);
  }

  // 2. Verify Supabase Auth user exists
  const { data: authUserData, error: authUserErr } = await supabase.auth.admin.getUserById(matchedAdmin.auth_user_id);
  if (authUserErr || !authUserData?.user) {
    console.error('\n❌ Error: Supabase Auth identity record not found for admin user.\n');
    if (options.throwOnError) throw new Error('Auth user identity not found');
    process.exit(1);
  }

  console.log(`✅ Administrator verified: ${matchedAdmin.username} (Role: ${matchedAdmin.role})`);
  console.log('----------------------------------------------------------------');
  console.log('Password requirements:');
  console.log(' • Minimum 10 characters');
  console.log(' • At least one uppercase letter (A-Z)');
  console.log(' • At least one lowercase letter (a-z)');
  console.log(' • At least one number (0-9)');
  console.log(' • At least one special character (!@#$%^&*...)');
  console.log('----------------------------------------------------------------\n');

  // 3. Interactive Secure Password Prompts (Hidden / Masked)
  let newPassword = options.newPassword;
  let confirmPassword = options.confirmPassword;

  if (!newPassword) {
    newPassword = await promptHidden('Enter new admin password: ');
  }

  const strengthCheck = validatePasswordStrength(newPassword);
  if (!strengthCheck.valid) {
    console.error(`\n❌ Weak Password: ${strengthCheck.message}\n`);
    if (options.throwOnError) throw new Error(strengthCheck.message);
    process.exit(1);
  }

  if (!confirmPassword) {
    confirmPassword = await promptHidden('Confirm new admin password: ');
  }

  if (newPassword !== confirmPassword) {
    console.error('\n❌ Error: Passwords do not match. Reset aborted.\n');
    if (options.throwOnError) throw new Error('Passwords do not match');
    process.exit(1);
  }

  // 4. Update Password in Supabase Auth (authoritative)
  console.log('\nApplying secure password update to Supabase Auth...');
  const { error: updateErr } = await supabase.auth.admin.updateUserById(matchedAdmin.auth_user_id, {
    password: newPassword,
    email_confirm: true
  });

  if (updateErr) {
    console.error('❌ Supabase Auth Update Error:', updateErr.message);
    if (options.throwOnError) throw updateErr;
    process.exit(1);
  }

  // 5. Update timestamp in aivekai_admin_users
  try {
    await supabase
      .from('aivekai_admin_users')
      .update({ updated_at: new Date().toISOString() })
      .eq('id', matchedAdmin.id);
  } catch (dbErr) {
    // Non-blocking
  }

  // 6. Security Audit Log
  console.log('================================================================');
  console.log(' ✅ PASSWORD RESET SUCCESSFUL                                   ');
  console.log('================================================================');
  console.log(`Administrator : ${matchedAdmin.username}`);
  console.log(`Mechanism     : Interactive CLI Recovery`);
  console.log(`Timestamp     : ${new Date().toISOString()}`);
  console.log(`Status        : Active & Secure`);
  console.log('================================================================');
  console.log('Sign in at: https://mozarex.com/aivekai/admin/login\n');

  return { success: true, username: matchedAdmin.username };
}

module.exports = { runPasswordReset, validatePasswordStrength };

if (require.main === module) {
  const target = process.argv[2];
  runPasswordReset(target);
}
