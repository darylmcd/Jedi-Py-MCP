# ADR 0002 Deepest workspace root

Date 2026-11-13

Status Accepted

## Context

A registered checkout could capture requests for a Git worktree or Python project nested inside it. The server then used the enclosing checkout's backend and configuration for the nested project.

## Decision

Select the closest registered root or project marker when walking from the supplied directory or the file's parent. Treat Git and Python project markers equally at each directory level.

## Migration

A call that selects a nested workspace can no longer include files outside that workspace, even when the enclosing checkout is registered. Split scans and file lists into one call per workspace. Use another tool for a move across workspace boundaries or an atomic transaction spanning multiple workspaces.
