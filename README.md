# Conduvera Contracts

This public repository is the canonical source for versioned Conduvera
protocol schemas, SDK contract bindings, the protocol test kit, and explicitly
selected stateless reference components.

## Authority boundary

Content in this repository may define data shapes, compatibility rules,
fixtures, and deterministic conformance behavior. Consumers bind contracts by
an exact repository commit and artifact digest; a moving branch is never a
contract release.

This repository has no authority over:

- runtime state or state stores;
- scheduler execution or workflow transitions;
- provider, GitHub, product, or merge mutations;
- credentials or credential handling;
- candidate, decision, evidence, marker, or journal stores;
- product-specific policy; or
- approval, merge, or deployment decisions.

Operational control-plane code does not belong here.

## Bootstrap state

The repository is intentionally initialized without published schemas or a
contract release. [`schema-index.yaml`](schema-index.yaml) is the canonical
machine-readable declaration of this empty bootstrap state. Later contract
releases must version and hash every published artifact.

## Content areas

- [`schemas/`](schemas/) contains versioned declarative protocol schemas.
- [`sdk/`](sdk/) contains contract bindings without operational authority.
- [`protocol-test-kit/`](protocol-test-kit/) contains non-mutating conformance
  fixtures and test definitions.
- [`selected-stateless-reference-components/`](selected-stateless-reference-components/)
  contains only explicitly admitted pure, deterministic references.
