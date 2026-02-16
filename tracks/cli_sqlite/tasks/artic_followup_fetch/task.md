artic task: artic_followup_fetch.

Goal:
1) Search artworks with GET /artworks/search using query term "monet".
2) Take the first result id from the search response.
3) Fetch details for that id with GET /artworks/{id}.
4) Report `id`, `title`, and `artist_title` from the follow-up response.

Constraints:
- Use run_artic for both API calls.
- Use query params for the search request.
- Build the follow-up path from the returned id.
