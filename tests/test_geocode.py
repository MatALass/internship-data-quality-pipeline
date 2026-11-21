from stages_cleaning.geocode import simplified_address_queries


def test_simplified_queries_never_use_city_alone():
    queries = simplified_address_queries("12 rue X, bureau 3", "Paris")
    assert queries
    assert all(query != "Paris" for query, _ in queries)
    assert all("Paris" in query for query, _ in queries)
