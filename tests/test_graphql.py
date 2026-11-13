"""GraphQL: два запроса к одному полю с разным набором полей."""

from tests.test_api import ADMIN, USER, auth, register, token_for


def gql(client, query, token=None, variables=None):
    headers = auth(token) if token else {}
    return client.post("/graphql", json={"query": query, "variables": variables or {}}, headers=headers)


def test_same_field_different_selection(client):
    register(client)
    token = token_for(client, ADMIN)

    # Запрос 1: только email
    short = gql(client, "{ users { email } }", token).json()
    assert "errors" not in short
    for u in short["data"]["users"]:
        assert set(u) == {"email"}

    # Запрос 2: то же поле users, но полный набор данных
    full = gql(client, "{ users { id email role createdAt } }", token).json()
    assert "errors" not in full
    for u in full["data"]["users"]:
        assert set(u) == {"id", "email", "role", "createdAt"}

    emails = {u["email"] for u in full["data"]["users"]}
    assert {USER["email"], ADMIN["email"]} <= emails


def test_me_query(client):
    register(client)
    data = gql(client, "{ me { email role } }", token_for(client, USER)).json()
    assert data["data"]["me"] == {"email": USER["email"], "role": "user"}


def test_arguments_and_variables(client):
    register(client)
    token = token_for(client, ADMIN)
    data = gql(client, "query($role: Role) { users(role: $role) { email } }", token, {"role": "admin"}).json()
    assert data["data"]["users"] == [{"email": ADMIN["email"]}]


def test_several_entities_in_one_request(client):
    register(client)
    token = token_for(client, ADMIN)
    data = gql(client, "{ me { email } usersStats { total admins users } }", token).json()
    assert data["data"]["me"]["email"] == ADMIN["email"]
    assert data["data"]["usersStats"] == {"total": 2, "admins": 1, "users": 1}


def test_without_token_returns_error(client):
    data = gql(client, "{ me { email } }").json()
    assert data["data"] is None
    assert "авторизация" in data["errors"][0]["message"]


def test_users_forbidden_for_role_user(client):
    register(client)
    data = gql(client, "{ users { email } }", token_for(client, USER)).json()
    assert data["data"] is None
    assert "admin" in data["errors"][0]["message"]


def test_graphiql_page(client):
    r = client.get("/graphql", headers={"Accept": "text/html"})
    assert r.status_code == 200
    assert "graphiql" in r.text.lower()
