-- Migration: align users.id and products.id foreign keys to UUID for PostgreSQL/Supabase
-- Safe to run multiple times.
-- Requires pgcrypto extension for gen_random_uuid() only if fallback generation is needed.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
DECLARE
    rec RECORD;
BEGIN
    -- Ensure users.id is UUID
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name = 'id'
          AND data_type <> 'uuid'
    ) THEN
        ALTER TABLE users
            ALTER COLUMN id TYPE uuid
            USING (
                CASE
                    WHEN id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN id::text::uuid
                    ELSE gen_random_uuid()
                END
            );
    END IF;

    -- Ensure products.id is UUID
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'products'
          AND column_name = 'id'
          AND data_type <> 'uuid'
    ) THEN
        ALTER TABLE products
            ALTER COLUMN id TYPE uuid
            USING (
                CASE
                    WHEN id::text ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN id::text::uuid
                    ELSE gen_random_uuid()
                END
            );
    END IF;

    -- List every FK column that should match users.id or products.id UUID type.
    FOR rec IN
        SELECT *
        FROM (VALUES
            ('email_tokens', 'user_id', FALSE),
            ('email_delivery_logs', 'recipient_user_id', TRUE),
            ('email_delivery_logs', 'triggered_by_user_id', TRUE),
            ('orders', 'user_id', FALSE),
            ('chats', 'user_id', TRUE),
            ('wishlist_items', 'user_id', FALSE),
            ('virtual_consultations', 'user_id', TRUE),
            ('client_room_uploads', 'user_id', TRUE),
            ('virtual_projects', 'assigned_designer_id', TRUE),
            ('project_progress', 'updated_by_user_id', TRUE),
            ('appointment_bookings', 'user_id', TRUE),
            ('appointment_bookings', 'designer_id', TRUE),
            ('designer_assignments', 'designer_id', TRUE),
            ('designer_assignments', 'assigned_by_user_id', TRUE),
            ('order_items', 'product_id', FALSE),
            ('wishlist_items', 'product_id', FALSE),
            ('chats', 'product_id', TRUE)
        ) AS t(table_name, column_name, is_nullable)
    LOOP
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = rec.table_name
              AND column_name = rec.column_name
              AND data_type <> 'uuid'
        ) THEN
            EXECUTE format(
                'ALTER TABLE %I ALTER COLUMN %I TYPE uuid USING (CASE WHEN %I IS NULL THEN NULL WHEN %I::text ~* ''^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'' THEN %I::text::uuid ELSE NULL END)',
                rec.table_name,
                rec.column_name,
                rec.column_name,
                rec.column_name,
                rec.column_name
            );
        END IF;
    END LOOP;
END $$;

COMMIT;
