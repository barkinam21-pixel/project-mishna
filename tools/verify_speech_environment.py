"""Read only GitHub protection metadata. Never request or display secret values."""
import json,os,urllib.request

def validate_environment(environment,policies):
    rules=environment.get('protection_rules',[])
    reviewers=[rule for rule in rules if rule.get('type')=='required_reviewers']
    # Manual dispatch on reviewed main replaces the optional human review gate.
    # Keep any configured reviewer rule; reject a sole-owner deadlock.
    if any(x.get('prevent_self_review') for x in reviewers):
        raise ValueError('Sole owner cannot approve own run with prevent_self_review enabled')
    deployment=environment.get('deployment_branch_policy') or {}
    if not deployment.get('custom_branch_policies') or deployment.get('protected_branches'):
        raise ValueError('Require explicit main-only deployment branch policy')
    branches=policies.get('branch_policies',[])
    if len(branches)!=1 or branches[0].get('name')!='main' or branches[0].get('type','branch')!='branch':
        raise ValueError('Only main branch may deploy; no tags or wildcard policies')
    if environment.get('can_admins_bypass') is not False:
        raise ValueError('Disable administrator bypass for this environment')


def main():
    base='https://api.github.com/repos/barkinam21-pixel/project-mishna/environments/azure-speech'
    def read(url):
        request=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
        with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
    validate_environment(read(base),read(base+'/deployment-branch-policies'))
    print('GITHUB_MAIN_ONLY_PROTECTIONS_VERIFIED')

if __name__=='__main__':
    try:main()
    except Exception as e:
        # Policy errors are our fixed strings; never expose HTTP responses or tokens.
        print(str(e) if isinstance(e,ValueError) else 'ENVIRONMENT_VERIFICATION_UNAVAILABLE; no protected job may proceed')
        raise SystemExit(2)
