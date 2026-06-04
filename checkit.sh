#!/bin/bash

OWNER="selfhosthub"   # confirm this is the right owner
REPOS=(studio studio-console studio-community studio-dev studio-cat studio-mark studio-plus)
OUT="security-audit-$(date +%Y%m%d-%H%M%S).txt"

{
  for r in "${REPOS[@]}"; do
    echo "════════ $r ════════"

    echo "-- repo basics --"
    gh api "repos/$OWNER/$r" \
      --jq '{visibility:.visibility, fork_allowed:.allow_forking, default_branch:.default_branch, archived:.archived}' 2>/dev/null \
      || echo "repo NOT FOUND at $OWNER/$r"

    echo "-- security_and_analysis --"
    gh api "repos/$OWNER/$r" --jq '.security_and_analysis' 2>/dev/null

    echo -n "-- dependabot alerts: "
    gh api "repos/$OWNER/$r/vulnerability-alerts" >/dev/null 2>&1 && echo enabled || echo disabled

    echo -n "-- private vuln reporting: "
    gh api "repos/$OWNER/$r/private-vulnerability-reporting" --jq '.enabled' 2>/dev/null || echo "n/a"

    echo "-- branch protection (main) --"
    gh api "repos/$OWNER/$r/branches/main/protection" \
      --jq '{enforce_admins:.enforce_admins.enabled, required_pr:(.required_pull_request_reviews!=null), force_push:.allow_force_pushes.enabled, deletions:.allow_deletions.enabled}' 2>/dev/null \
      || echo "none"

    echo "-- actions token perms --"
    gh api "repos/$OWNER/$r/actions/permissions/workflow" \
      --jq '{default:.default_workflow_permissions, can_approve_pr:.can_approve_pull_request_reviews}' 2>/dev/null

    echo "-- governance files --"
    gh api "repos/$OWNER/$r/community/profile" \
      --jq '.files | {security:(.security!=null), contributing:(.contributing!=null), license:.license.spdx_id, coc:(.code_of_conduct!=null)}' 2>/dev/null

    echo "-- direct collaborators --"
    gh api "repos/$OWNER/$r/collaborators?affiliation=direct" --jq '[.[].login]' 2>/dev/null

    echo "-- deploy keys --"
    gh api "repos/$OWNER/$r/keys" --jq '[.[] | {title, read_only}]' 2>/dev/null

    echo "-- webhooks --"
    gh api "repos/$OWNER/$r/hooks" --jq '[.[].config.url]' 2>/dev/null
    echo
  done

  echo "════════ ACCOUNT ════════"
  gh api user --jq '{twofa:.two_factor_authentication}' 2>/dev/null
  echo "-- ssh keys --"
  gh api user/keys --jq '[.[].title]' 2>/dev/null
} | tee "$OUT"

echo
echo "Saved to $OUT"
