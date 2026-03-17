from src.models import User


def test_user_name() -> None:
    user = User(user_id=1, name="Ada")
    assert user.name == "Ada"
