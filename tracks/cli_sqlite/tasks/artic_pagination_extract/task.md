artic task: artic_pagination_extract.

Goal:
1) Call GET /artworks/search for query term "portrait".
2) Use pagination params `page=2` and `limit=3`.
3) Restrict fields to `id,title,artist_title`.
4) Return the 3 rows from page 2 and list each row as `id | title | artist_title`.

Constraints:
- Use run_artic with method GET.
- Pass pagination and fields in the query object.
- Return only data from page 2.
