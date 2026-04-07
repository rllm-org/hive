def test_email_module_has_sender():
    from hive.server import email

    assert "Hive" in email.EMAIL_FROM
