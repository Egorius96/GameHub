from app.core.reserved_usernames import is_reserved_username, is_system_service_username


def test_reserved_usernames():
    assert is_reserved_username("admindb")
    assert is_reserved_username("DATABASE")
    assert is_reserved_username(" database ")
    assert not is_reserved_username("misha")


def test_system_service_usernames():
    assert is_system_service_username("admindb")
    assert is_system_service_username("database")
    assert not is_system_service_username("player1")
