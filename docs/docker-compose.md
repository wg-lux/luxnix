# Documentation Docker Compose example

This is the preserved Compose example previously stored as
`docs/docker-compose.yml`. It is reference material, not a runnable Compose
file. The volume mapping and image are reproduced unchanged; validate the
mount path, repository-root MkDocs configuration, and required plugins before
using it for a local preview.

```yaml
services:
  docs:
    image: squidfunk/mkdocs-material:9.5.31
    volumes:
      - ./:docs
    ports:
      - 8000:8000
```
