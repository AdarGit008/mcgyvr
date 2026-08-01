// Tree-plane facts: the repo's declared self (the descriptor) and other at-rest signals the
// derivations consume. Deliberately thin for now — the descriptor is the load-bearing tree
// fact; more (manifests, workflow files) join here as later derivations need them.
import { loadDescriptor } from '../descriptor.mjs'

export function treeFacts(repo, descriptor) {
  const d = descriptor || loadDescriptor(repo)
  return {
    available: true,
    descriptor: { present: d.present, valid: d.valid, type: d.data?.type ?? null, workflow: d.data?.workflow ?? null, errors: d.errors || [] },
  }
}
