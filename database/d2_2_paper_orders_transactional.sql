-- ==============================================================================
-- StockAnalysis Stage D2.2 / D2.3A.1: Transactional PostgreSQL Order Management Migration
-- Namespace: schema 'stockanalysis'
-- Objectives:
-- 1. Create stockanalysis.paper_orders (with versioning, optimistic concurrency, unique client_order_id,
--    and strict regex-enforced paper-account validation: ^(DU|DF)[A-Z0-9]{3,28}$).
-- 2. Create stockanalysis.paper_order_events (append-only immutable audit trail with DB trigger).
-- 3. Create stockanalysis.paper_execution_claims (atomic distributed lease/claim mechanics via partial unique index).
-- 4. Scope schema permissions strictly to stockanalysis_app (paper_order_events is strictly SELECT, INSERT).
-- 5. Safe, validated legacy reconciliation from stockanalysis.system_settings (fails visibly on error).
-- ==============================================================================

BEGIN;

-- 1. Ensure Schema
CREATE SCHEMA IF NOT EXISTS stockanalysis;

-- 2. Create Table: stockanalysis.paper_orders
CREATE TABLE IF NOT EXISTS stockanalysis.paper_orders (
    order_id VARCHAR(50) PRIMARY KEY,
    client_order_id VARCHAR(100) UNIQUE NOT NULL,
    broker VARCHAR(20) NOT NULL DEFAULT 'ibkr',
    account_id VARCHAR(30) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL DEFAULT 'LIMIT',
    quantity NUMERIC(14, 4) NOT NULL,
    limit_price NUMERIC(14, 4) NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    estimated_notional NUMERIC(14, 4) NOT NULL,
    filled_quantity NUMERIC(14, 4) NOT NULL DEFAULT 0.0,
    avg_fill_price NUMERIC(14, 4),
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    version INTEGER NOT NULL DEFAULT 1,
    proposed_by VARCHAR(50) NOT NULL DEFAULT 'ADMIN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_by VARCHAR(50),
    approved_at TIMESTAMPTZ,
    approval_expires_at TIMESTAMPTZ,
    claimed_by_agent VARCHAR(50),
    claimed_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    requires_manual_reconciliation BOOLEAN NOT NULL DEFAULT FALSE,
    can_auto_resubmit BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    risk_check_json TEXT,
    execution_report_json TEXT,
    market_quote_json TEXT,
    CONSTRAINT chk_paper_orders_action CHECK (action IN ('BUY', 'SELL')),
    CONSTRAINT chk_paper_orders_type CHECK (order_type = 'LIMIT'),
    CONSTRAINT chk_paper_orders_qty CHECK (quantity > 0),
    CONSTRAINT chk_paper_orders_price CHECK (limit_price > 0),
    CONSTRAINT chk_paper_orders_notional CHECK (estimated_notional > 0),
    CONSTRAINT chk_paper_orders_fill_qty CHECK (filled_quantity >= 0 AND filled_quantity <= quantity),
    CONSTRAINT chk_paper_orders_avg_fill CHECK (avg_fill_price IS NULL OR avg_fill_price > 0),
    CONSTRAINT chk_paper_orders_version CHECK (version >= 1),
    CONSTRAINT chk_paper_orders_broker CHECK (broker IN ('ibkr', 'alpaca')),
    -- Broker-aware paper account validation (strict DU/DF for IBKR; PA/UUID for Alpaca)
    CONSTRAINT chk_paper_orders_account CHECK (
        (broker = 'ibkr' AND account_id ~ '^(DU|DF)[A-Z0-9]{3,28}$') OR
        (broker = 'alpaca' AND (account_id ~ '^PA[A-Z0-9]{5,28}$' OR account_id ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'))
    ),
    CONSTRAINT chk_paper_orders_status CHECK (
        status IN (
            'DRAFT',
            'RISK_CHECKED',
            'AWAITING_APPROVAL',
            'APPROVED',
            'CLAIMED',
            'SUBMITTING',
            'SUBMITTED',
            'PARTIALLY_FILLED',
            'FILLED',
            'CANCELLED',
            'REJECTED',
            'EXPIRED',
            'UNKNOWN'
        )
    )
);

-- Indexes on paper_orders
CREATE INDEX IF NOT EXISTS idx_paper_orders_status ON stockanalysis.paper_orders(status);
CREATE INDEX IF NOT EXISTS idx_paper_orders_broker ON stockanalysis.paper_orders(broker);
CREATE INDEX IF NOT EXISTS idx_paper_orders_account ON stockanalysis.paper_orders(account_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_broker_account ON stockanalysis.paper_orders(broker, account_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_symbol ON stockanalysis.paper_orders(symbol);
CREATE INDEX IF NOT EXISTS idx_paper_orders_created ON stockanalysis.paper_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_paper_orders_approval_exp ON stockanalysis.paper_orders(approval_expires_at) WHERE status = 'APPROVED';
CREATE INDEX IF NOT EXISTS idx_paper_orders_claimed ON stockanalysis.paper_orders(claimed_by_agent) WHERE status IN ('CLAIMED', 'SUBMITTING');
CREATE INDEX IF NOT EXISTS idx_paper_orders_reconciliation ON stockanalysis.paper_orders(requires_manual_reconciliation) WHERE requires_manual_reconciliation = TRUE;

-- 3. Create Table: stockanalysis.paper_order_events (Append-only audit trail)
CREATE TABLE IF NOT EXISTS stockanalysis.paper_order_events (
    id BIGSERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL REFERENCES stockanalysis.paper_orders(order_id) ON DELETE CASCADE,
    event_sequence INTEGER NOT NULL,
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    action VARCHAR(50) NOT NULL,
    actor VARCHAR(50) NOT NULL,
    reason TEXT,
    event_data_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_order_events_seq CHECK (event_sequence >= 1),
    CONSTRAINT uq_order_event_sequence UNIQUE (order_id, event_sequence)
);

CREATE INDEX IF NOT EXISTS idx_order_events_order_id ON stockanalysis.paper_order_events(order_id);
CREATE INDEX IF NOT EXISTS idx_order_events_created ON stockanalysis.paper_order_events(created_at);

-- 4. Create Table: stockanalysis.paper_execution_claims (Atomic distributed claim tracking)
CREATE TABLE IF NOT EXISTS stockanalysis.paper_execution_claims (
    claim_id VARCHAR(50) PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL REFERENCES stockanalysis.paper_orders(order_id) ON DELETE CASCADE,
    agent_id VARCHAR(50) NOT NULL,
    broker VARCHAR(20) NOT NULL DEFAULT 'ibkr',
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_expires_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    released_at TIMESTAMPTZ,
    release_reason VARCHAR(100),
    CONSTRAINT chk_claims_broker CHECK (broker IN ('ibkr', 'alpaca'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_claim_order ON stockanalysis.paper_execution_claims(order_id) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_claims_agent ON stockanalysis.paper_execution_claims(agent_id);
CREATE INDEX IF NOT EXISTS idx_claims_lease_exp ON stockanalysis.paper_execution_claims(lease_expires_at) WHERE is_active = TRUE;

-- 5. Audit Trail Immutability (Engine-enforced append-only trigger)
CREATE OR REPLACE FUNCTION stockanalysis.prevent_audit_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'AUDIT TRAIL IMMUTABLE: UPDATE and DELETE operations on stockanalysis.paper_order_events are strictly prohibited (Order ID: %, Event Sequence: %).', OLD.order_id, OLD.event_sequence;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_audit_event_mutation ON stockanalysis.paper_order_events;
CREATE TRIGGER trg_prevent_audit_event_mutation
BEFORE UPDATE OR DELETE ON stockanalysis.paper_order_events
FOR EACH ROW
EXECUTE FUNCTION stockanalysis.prevent_audit_event_mutation();

-- 6. Scope Schema Grants Strictly to StockAnalysis Runtime Role
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'stockanalysis_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON stockanalysis.paper_orders TO stockanalysis_app;
        -- Audit events table is strictly append-only: NO UPDATE, NO DELETE granted
        GRANT SELECT, INSERT ON stockanalysis.paper_order_events TO stockanalysis_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON stockanalysis.paper_execution_claims TO stockanalysis_app;
        GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA stockanalysis TO stockanalysis_app;
    END IF;
END
$$;

-- 7. Legacy Reconciliation / Migration Helper Procedure
-- Validates records against strict paper account invariants and fails visibly on errors
DO $$
DECLARE
    json_record TEXT;
    orders_array JSONB;
    order_item JSONB;
    audit_item JSONB;
    seq_counter INTEGER;
    bound_acc_record TEXT;
    bound_account_val VARCHAR(30);
    order_acc_id VARCHAR(30);
BEGIN
    -- Look up bound paper account from system settings
    SELECT value INTO bound_acc_record FROM stockanalysis.system_settings WHERE key = 'ibkr_bound_paper_account';
    IF bound_acc_record IS NOT NULL AND bound_acc_record != '' THEN
        BEGIN
            bound_account_val := (bound_acc_record::JSONB)->>'account_id';
        EXCEPTION WHEN OTHERS THEN
            bound_account_val := NULL;
        END;
    END IF;

    SELECT value INTO json_record FROM stockanalysis.system_settings WHERE key = 'ibkr_paper_orders';
    IF json_record IS NOT NULL AND json_record != '' THEN
        BEGIN
            orders_array := json_record::JSONB;
            FOR order_item IN SELECT * FROM jsonb_array_elements(orders_array)
            LOOP
                -- Validate paper account identity
                order_acc_id := COALESCE(order_item->>'account_id', bound_account_val);
                IF order_acc_id IS NULL OR order_acc_id !~ '^(DU|DF)[A-Z0-9]{3,28}$' THEN
                    RAISE EXCEPTION 'Legacy D2.1 JSON reconciliation failed: Order % has invalid paper account "%" (bound account: "%")',
                        order_item->>'order_id', order_acc_id, bound_account_val;
                END IF;

                -- Insert order if not already present
                IF NOT EXISTS (SELECT 1 FROM stockanalysis.paper_orders WHERE order_id = (order_item->>'order_id')) THEN
                    INSERT INTO stockanalysis.paper_orders (
                        order_id,
                        client_order_id,
                        broker,
                        account_id,
                        symbol,
                        action,
                        order_type,
                        quantity,
                        limit_price,
                        currency,
                        estimated_notional,
                        filled_quantity,
                        status,
                        version,
                        proposed_by,
                        created_at,
                        updated_at,
                        approved_by,
                        approved_at,
                        approval_expires_at,
                        claimed_by_agent,
                        claimed_at,
                        submitted_at,
                        requires_manual_reconciliation,
                        can_auto_resubmit,
                        notes,
                        risk_check_json,
                        execution_report_json
                    ) VALUES (
                        order_item->>'order_id',
                        COALESCE(order_item->>'client_idempotency_key', order_item->>'order_id'),
                        COALESCE(order_item->>'broker', 'ibkr'),
                        order_acc_id,
                        COALESCE(order_item->>'symbol', 'AAPL'),
                        COALESCE(order_item->>'action', 'BUY'),
                        COALESCE(order_item->>'order_type', 'LIMIT'),
                        COALESCE((order_item->>'quantity')::NUMERIC, 1.0),
                        COALESCE((order_item->>'limit_price')::NUMERIC, 100.0),
                        COALESCE(order_item->>'currency', 'USD'),
                        COALESCE((order_item->>'estimated_notional')::NUMERIC, 100.0),
                        COALESCE((order_item->>'filled_quantity')::NUMERIC, 0.0),
                        COALESCE(order_item->>'status', 'DRAFT'),
                        1,
                        COALESCE(order_item->>'proposed_by', 'ADMIN'),
                        COALESCE((order_item->>'created_at')::TIMESTAMPTZ, NOW()),
                        COALESCE((order_item->>'updated_at')::TIMESTAMPTZ, NOW()),
                        order_item->>'approved_by',
                        (order_item->>'approved_at')::TIMESTAMPTZ,
                        (order_item->>'approval_expires_at')::TIMESTAMPTZ,
                        order_item->>'claimed_by_agent',
                        (order_item->>'claimed_at')::TIMESTAMPTZ,
                        (order_item->>'submitted_at')::TIMESTAMPTZ,
                        COALESCE((order_item->>'requires_manual_reconciliation')::BOOLEAN, FALSE),
                        COALESCE((order_item->>'can_auto_resubmit')::BOOLEAN, FALSE),
                        order_item->>'notes',
                        order_item->>'risk_check',
                        order_item->>'execution_report'
                    );

                    -- Reconstruct immutable audit events
                    seq_counter := 1;
                    IF order_item ? 'audit_trail' AND jsonb_typeof(order_item->'audit_trail') = 'array' THEN
                        FOR audit_item IN SELECT * FROM jsonb_array_elements(order_item->'audit_trail')
                        LOOP
                            INSERT INTO stockanalysis.paper_order_events (
                                order_id,
                                event_sequence,
                                from_status,
                                to_status,
                                action,
                                actor,
                                reason,
                                created_at
                            ) VALUES (
                                order_item->>'order_id',
                                seq_counter,
                                audit_item->>'from_status',
                                COALESCE(audit_item->>'to_status', order_item->>'status'),
                                COALESCE(audit_item->>'action', 'STATUS_CHANGE'),
                                COALESCE(audit_item->>'actor', 'SYSTEM'),
                                audit_item->>'reason',
                                COALESCE((audit_item->>'timestamp')::TIMESTAMPTZ, NOW())
                            );
                            seq_counter := seq_counter + 1;
                        END LOOP;
                    END IF;
                END IF;
            END LOOP;
        EXCEPTION WHEN OTHERS THEN
            -- Fail visibly: abort transaction and report exact failure reason
            RAISE EXCEPTION 'CRITICAL MIGRATION FAILURE: Legacy D2.1 JSON reconciliation failed: %', SQLERRM;
        END;
    END IF;
END
$$;

COMMIT;
