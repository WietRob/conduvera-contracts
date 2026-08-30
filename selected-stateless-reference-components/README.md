# Selected stateless reference components

This directory is reserved for explicitly selected, pure, deterministic
reference components whose behavior is part of a published contract. It is
intentionally empty at bootstrap.

Reference content must remain stateless and non-operational. It cannot own a
scheduler, state store, mutation path, credentials, or product-specific
policy.
