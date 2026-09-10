require('dotenv').config();
const { createClient } = require('@supabase/supabase-js');
const crypto = require('crypto');

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_KEY;

if (!supabaseUrl || !supabaseKey) {
  console.error('❌ Error: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing from environment.');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

async function provisionAdmin({ username = 'admin', email = null, password }) {
  if (!username || !password) {
    console.error('❌ Usage: node create-admin-user.js <username> <password> [email]');
    console.error('Example: node create-admin-user.js admin MySecurePassword123! info@mozarex.com');
    process.exit(1);
  }

  const normalizedUsername = username.toLowerCase().trim();
  const adminEmail = email ? email.toLowerCase().trim() : `${normalizedUsername}@admin.aivekai.internal`;

  console.log(`\n================================================================`);
  console.log(` PROVISIONING AIVEKAI ADMINISTRATOR ACCOUNT                     `);
  console.log(`================================================================`);
  console.log(`Username : ${normalizedUsername}`);
  console.log(`Auth Email: ${adminEmail}`);

  try {
    // 1. Check if auth user exists in Supabase Auth
    let authUser = null;
    const { data: { users }, error: listErr } = await supabase.auth.admin.listUsers();
    if (listErr) {
      console.error('Error listing auth users:', listErr.message);
    } else {
      authUser = users.find(u => u.email === adminEmail);
    }

    if (authUser) {
      console.log(`Found existing Supabase Auth user (${authUser.id}). Updating password...`);
      const { data: updatedUser, error: updateErr } = await supabase.auth.admin.updateUserById(authUser.id, {
        password: password,
        email_confirm: true
      });
      if (updateErr) {
        throw new Error(`Failed to update auth user password: ${updateErr.message}`);
      }
      authUser = updatedUser.user;
      console.log('✅ Password successfully updated in Supabase Auth.');
    } else {
      console.log('Creating new user in Supabase Auth...');
      const { data: createdUser, error: createErr } = await supabase.auth.admin.createUser({
        email: adminEmail,
        password: password,
        email_confirm: true
      });
      if (createErr) {
        throw new Error(`Failed to create auth user: ${createErr.message}`);
      }
      authUser = createdUser.user;
      console.log(`✅ Auth user created (${authUser.id}).`);
    }

    // 2. Check if aivekai_admin_users record exists
    const { data: existingAdmin, error: adminQueryErr } = await supabase
      .from('aivekai_admin_users')
      .select('*')
      .ilike('username', normalizedUsername)
      .maybeSingle();

    if (existingAdmin) {
      console.log(`Updating existing aivekai_admin_users record (${existingAdmin.id})...`);
      const { error: patchErr } = await supabase
        .from('aivekai_admin_users')
        .update({
          auth_user_id: authUser.id,
          role: 'admin',
          is_active: true,
          updated_at: new Date().toISOString()
        })
        .eq('id', existingAdmin.id);

      if (patchErr) {
        throw new Error(`Failed to update aivekai_admin_users: ${patchErr.message}`);
      }
      console.log('✅ Updated aivekai_admin_users table record.');
    } else {
      console.log('Inserting new record into aivekai_admin_users...');
      const { error: insertErr } = await supabase
        .from('aivekai_admin_users')
        .insert([{
          id: crypto.randomUUID(),
          auth_user_id: authUser.id,
          username: normalizedUsername,
          role: 'admin',
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }]);

      if (insertErr) {
        throw new Error(`Failed to insert into aivekai_admin_users: ${insertErr.message}`);
      }
      console.log('✅ Created new aivekai_admin_users table record.');
    }

    console.log(`\n================================================================`);
    console.log(` 🎉 ADMIN ACCOUNT READY!                                        `);
    console.log(`================================================================`);
    console.log(`You can now sign in at: https://mozarex.com/aivekai/admin/login`);
    console.log(`Username: ${normalizedUsername}`);
    console.log(`================================================================\n`);
  } catch (err) {
    console.error('❌ Provisioning Error:', err.message);
    process.exit(1);
  }
}

const args = process.argv.slice(2);
const username = args[0] || 'admin';
const password = args[1];
const email = args[2] || null;

if (!password) {
  console.log('Usage: node create-admin-user.js <username> <password> [email]');
  console.log('Example: node create-admin-user.js admin YourSecurePassword123! info@mozarex.com');
  process.exit(0);
}

provisionAdmin({ username, password, email });
