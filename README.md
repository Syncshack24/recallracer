# Quickstart

```
make serve-frontend
```

To start the backend, execute

```
make serve-backend
```

**UI Library:** We're using [Mantine UI](https://mantine.dev/) as the component library for the frontend. It provides free [prebuilt designs](https://ui.mantine.dev/) for annoying stuff like navigation bars and notifications.

## Database

Should we need a database, there are scripts for starting PostgreSQL and MongoDB as docker containers.

- `make postgres-up` : Start postgres in a container
- `make postgres-down` : Stop postgres container
- `make mongo-up` : Start mongo in a container
- `make mongo-down` : Stop mongo container

## Local mail sending

Should we have a mail-sending feature, there is a script for starting a local email storage using mailhog in a container.

- `make mailhog-up` : Start mailhog in a container
- `make mailhog-down` : Stop mailhog container
