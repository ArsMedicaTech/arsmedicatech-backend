from lib.models.api_key import APIKey


def main():
    # test_key = APIKey(
    #     id="id",
    #     name="name",
    #     user_id="user_id",
    #     is_active=True,
    #     permissions=["admin:delete"],
    # )
    test_key = APIKey.model_validate(
        {
            "name": "self.name",
            "user_id": "self.user_id",
            "key_hash": "self.key_hash",
            "permissions": ["admin:delete"],
            "rate_limit_per_hour": 1000,
            "is_active": True,
        }
    )
    print(test_key.model_dump())


if __name__ == "__main__":
    main()
