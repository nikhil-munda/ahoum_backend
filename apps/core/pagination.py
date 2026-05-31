from rest_framework.pagination import PageNumberPagination


class StandardResultsPagination(PageNumberPagination):
    """
    Returns: {"count": int, "next": url|null, "previous": url|null, "results": [...]}
    Callers may override page_size per-request via ?page_size=N (max 100).
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
