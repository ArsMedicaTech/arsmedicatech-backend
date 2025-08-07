"""
Migration script to set up webhook subscriptions table
"""
from amt_nano.db.surreal import DbController

from settings import logger


def setup_webhook_subscriptions_table():
    """
    Set up the webhook_subscription table in SurrealDB
    """
    db = DbController()
    try:
        db.connect()
        
        # Create webhook_subscription table
        logger.info("Creating webhook_subscription table...")
        
        result = db.query(schema_query, {})
        logger.info(f"Schema creation result: {result}")
        
        # Create some sample webhook subscriptions for testing
        logger.info("Creating sample webhook subscriptions...")
        
        sample_subscriptions = [
            {
                "event_name": "appointment.created",
                "target_url": "https://webhook.site/your-unique-url",
                "secret": "your-secret-key-here",
                "enabled": True
            },
            {
                "event_name": "appointment.cancelled",
                "target_url": "https://webhook.site/your-unique-url",
                "secret": "your-secret-key-here",
                "enabled": True
            }
        ]
        
        for subscription in sample_subscriptions:
            result = db.create('webhook_subscription', subscription)
            if result:
                logger.info(f"Created sample subscription: {result.get('id')}")
            else:
                logger.error(f"Failed to create sample subscription: {subscription}")
        
        logger.info("Webhook subscriptions table setup completed successfully!")
        
    except Exception as e:
        logger.error(f"Error setting up webhook subscriptions table: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    setup_webhook_subscriptions_table() 