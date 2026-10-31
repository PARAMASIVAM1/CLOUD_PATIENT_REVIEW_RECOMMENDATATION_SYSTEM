import traceback
from app import app

app.config["TESTING"] = True
client = app.test_client()

with client:
    with client.session_transaction() as sess:
        sess["logged_in"] = True
        sess["user_role"] = "patient"
        sess["user_email"] = "patient@example.com"
        sess["user_name"] = "Ramesh Kumar"

    try:
        res = client.get("/search?part=eyes&disease=Blurred%20Vision")
        print("Status code:", res.status_code)
    except Exception as e:
        traceback.print_exc()

