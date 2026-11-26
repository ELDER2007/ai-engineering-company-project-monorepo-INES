// Mirrors GET /auth/me (services/api/auth/schemas.py, MeOut) — keep in sync manually.
export type Role = "admin" | "manager" | "user";

/** `ProfileMe` in services/api/profiles/schemas.py: the editable data only (no storage id, no user_id). */
export interface Profile {
  name: string;
  contact_email: string | null;
  phone: string | null;
  address: string | null;
}

export interface Me {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  profile: Profile;
}

// Mirrors PUT /profiles/me (services/api/profiles/schemas.py, ProfileUpdate): omitted = unchanged,
// null = cleared (not allowed for name).
export interface ProfileUpdate {
  name?: string;
  phone?: string | null;
  address?: string | null;
}

// Mirrors POST /users (services/api/users/schemas.py, UserCreate / SignUpOut).
export interface SignUpPayload {
  email: string;
  password: string;
  name?: string;
  phone?: string;
  address?: string;
}

/** A generic confirmation, nothing else: the email is not echoed back by an unauthenticated flow. */
export interface SignUpOut {
  message: string;
}
