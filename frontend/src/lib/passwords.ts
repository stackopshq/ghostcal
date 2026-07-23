// Mirrors MIN_PASSWORD_LENGTH in the backend's application/passwords.py. The server is the
// authority and enforces this again — this only spares the user a round-trip to be told what the
// form could have said. The breach check has no client-side equivalent by design: the password
// must never leave the browser for us to hash it, so that answer only ever comes from the server.
export const MIN_PASSWORD_LENGTH = 12;
