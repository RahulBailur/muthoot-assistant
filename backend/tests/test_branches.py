from httpx import AsyncClient

from tests.helpers import make_branch


async def test_branch_locator_is_public(client: AsyncClient) -> None:
    await make_branch("Kochi")
    await make_branch("Chennai")

    response = await client.get("/api/branches")

    assert response.status_code == 200
    assert [b["city"] for b in response.json()] == ["Chennai", "Kochi"]


async def test_find_branches_by_city_or_pincode(client: AsyncClient) -> None:
    await make_branch("Kochi")
    await make_branch("Chennai")

    by_city = await client.get("/api/branches", params={"city": "CHENNAI"})
    by_pincode = await client.get("/api/branches", params={"pincode": "682011"})

    assert [b["city"] for b in by_city.json()] == ["Chennai"]
    assert len(by_pincode.json()) == 2  # the test branches share a pincode


async def test_branch_timings_are_readable(client: AsyncClient) -> None:
    branch = await make_branch()
    branch.open_weekdays = [0, 1, 2, 3, 4, 5]
    await branch.save()

    response = await client.get(f"/api/branches/{branch.id}")

    assert response.json()["timings"] == "Mon–Sat 09:30–17:30"


async def test_unknown_branch_is_404(client: AsyncClient) -> None:
    response = await client.get("/api/branches/0123456789abcdef01234567")

    assert response.status_code == 404
