URL = "/api/v1/categories"


def test_seeded_default_categories(categories):
    assert len(categories) == 15
    assert categories["food"]["name"] == "Ăn uống"
    assert categories["food"]["kind"] == "expense"
    assert categories["food"]["default_spending_type"] == "essential"
    assert categories["shopping"]["default_spending_type"] == "non_essential"
    assert categories["salary"]["kind"] == "income"
    assert categories["salary"]["default_spending_type"] is None
    assert all(c["is_system"] for c in categories.values())


def test_filter_by_kind(client):
    income = client.get(URL, params={"kind": "income"}).json()
    expense = client.get(URL, params={"kind": "expense"}).json()

    assert {c["slug"] for c in income} == {"salary", "freelance", "bonus", "other_income"}
    assert len(expense) == 11
    assert all(c["kind"] == "expense" for c in expense)


def test_create_custom_category_generates_slug(client):
    resp = client.post(
        URL,
        json={"name": "Thú cưng", "kind": "expense", "default_spending_type": "non_essential"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "thu_cung"
    assert body["is_system"] is False
    assert body["is_archived"] is False

    again = client.post(
        URL, json={"name": "Thú  cưng!", "kind": "expense", "default_spending_type": "essential"}
    )
    assert again.json()["slug"] == "thu_cung_2"


def test_create_category_validates_spending_type(client):
    income_with_type = client.post(
        URL, json={"name": "Cho thuê", "kind": "income", "default_spending_type": "essential"}
    )
    expense_without_type = client.post(URL, json={"name": "Cafe", "kind": "expense"})

    assert income_with_type.status_code == 422
    assert income_with_type.json()["code"] == "validation_error"
    assert expense_without_type.status_code == 422


def test_patch_is_system_rejected(client, categories):
    """Test case #8."""
    food_id = categories["food"]["id"]

    resp = client.patch(f"{URL}/{food_id}", json={"is_system": False})

    assert resp.status_code == 422
    assert client.get(URL).json()[0]["is_system"] is True


def test_patch_kind_or_slug_rejected(client, categories):
    food_id = categories["food"]["id"]

    assert client.patch(f"{URL}/{food_id}", json={"kind": "income"}).status_code == 422
    assert client.patch(f"{URL}/{food_id}", json={"slug": "x"}).status_code == 422


def test_patch_name_icon_and_default_spending_type(client, categories):
    food_id = categories["food"]["id"]

    resp = client.patch(
        f"{URL}/{food_id}",
        json={"name": "Ăn & uống", "icon": "🍲", "default_spending_type": "non_essential"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Ăn & uống"
    assert body["icon"] == "🍲"
    assert body["default_spending_type"] == "non_essential"
    assert body["slug"] == "food"


def test_patch_default_spending_type_respects_kind(client, categories):
    food = client.patch(f"{URL}/{categories['food']['id']}", json={"default_spending_type": None})
    salary = client.patch(
        f"{URL}/{categories['salary']['id']}", json={"default_spending_type": "essential"}
    )

    assert food.status_code == 422
    assert food.json()["code"] == "spending_type_required"
    assert salary.status_code == 422
    assert salary.json()["code"] == "income_spending_type"


def test_patch_rejects_null_name(client, categories):
    resp = client.patch(f"{URL}/{categories['food']['id']}", json={"name": None})

    assert resp.status_code == 422


def test_archive_hides_category_by_default(client, categories):
    other_id = categories["other"]["id"]

    resp = client.patch(f"{URL}/{other_id}", json={"is_archived": True})

    assert resp.status_code == 200
    visible = {c["slug"] for c in client.get(URL).json()}
    with_archived = {c["slug"] for c in client.get(URL, params={"include_archived": True}).json()}
    assert "other" not in visible
    assert "other" in with_archived


def test_patch_unknown_category_404(client):
    resp = client.patch(f"{URL}/00000000-0000-0000-0000-000000000000", json={"name": "x"})

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Không tìm thấy danh mục", "code": "category_not_found"}
