# ADR 0002: Git collaboration workflow

## Status

Accepted.

## Workflow

Create short-lived feature branches from `main`, keep each phase reviewable, and open a pull request
for review. CI runs on every push and pull request. After review and passing checks, squash merge so
`main` retains one coherent commit per change. Do not merge or deploy directly from a feature branch.

## Requiring CI on `main`

In the repository hosting settings, create a branch protection rule or ruleset targeting `main`.
Require pull requests before merging and require the workflow's `checks` job to pass. Consider also
requiring the branch to be current before merge and preventing force pushes and deletion.

This repository only contains the workflow and documentation. No remote branch-protection rule is
claimed to be enabled; that setting must be configured on the hosting service by an authorized
maintainer.

