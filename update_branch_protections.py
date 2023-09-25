from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, fields
from pathlib import Path
from typing import List

from update_github_settings import (BranchProtection, Repository,
                                    default_required_status_checks)

master_protect = BranchProtection()
gh_pages_prot = BranchProtection(pattern='gh-pages', allows_force_pushes=True,
                                 dismisses_stale_reviews=False,
                                 required_status_checks=[],
                                 requires_status_checks=False,
                                 required_approving_review_count=0,
                                 requires_approving_reviews=False,
                                 )
all_prot = BranchProtection(pattern='*', required_status_checks=[],
                            dismisses_stale_reviews=False,
                            requires_status_checks=False,
                            required_approving_review_count=0,
                            requires_approving_reviews=False,
                            allows_deletions=True,)


def str_to_bool(val: str):
    return val.lower() in ('y', 'yes', 'true')


@dataclass
class ProtectionGroup:
    owner: str
    repo_name: str
    repo_type: str
    master: bool = False
    gh_pages: bool = False
    default: bool = False

    # Map column names to protection rules
    RULE_MAP = {
        'master': master_protect,
        'gh_pages': gh_pages_prot,
        'default': all_prot
    }

    # map repo-types to status-check lists
    CHECK_NAME_MAP = {
        'Python Library': 'python',
        'Python Dev': 'none',
        'PLC': 'twincat',
        'TwinCAT Library': 'twincat',
        'Backup': 'none',
        'Other': 'none',
        'EPICS IOC': 'none',
        'Exempt': 'none',
        'External': 'none',
        'EPICS module': 'none'
    }

    @classmethod
    def from_dict(cls, source: dict):
        try:
            flags = {f.name: str_to_bool(source[f.name]) for f in fields(cls)
                     if f.name not in ('owner', 'repo_name', 'repo_type')}
        except KeyError as e:
            print("source data malformed, aborting")
            raise e

        return cls(
            owner=source["owner"],
            repo_name=source["repo_name"],
            repo_type=source["repo_type"],
            **flags
        )

    def apply_protections(
        self,
        write: bool
    ) -> None:
        repo = Repository.from_name(owner=self.owner, repo=self.repo_name)

        for prot in BranchProtection.from_repository(repo):
            if write:
                print("Deleting branch protection setting")
                prot.delete()
            else:
                print("(dry run) Deleting branch protection setting")

        rule_names = (f.name for f in fields(self)
                      if f.name not in ('owner', 'repo_name', 'repo_type'))

        for name in rule_names:
            if getattr(self, name, False):
                print(f'created {name} rule for repo: {self.repo_name}')
                if name == 'master':
                    protection_rule = BranchProtection()
                    # customize status checks based on repo type
                    check_name = self.CHECK_NAME_MAP.get(self.repo_type, 'none')
                    check_list = default_required_status_checks[check_name]
                    protection_rule.required_status_checks = check_list
                else:
                    protection_rule = self.RULE_MAP[name]

                if write:
                    protection_rule.create(repo)
                    print(f'-- {name} rule applied')
                else:
                    print('-- rule not applied')


def parse_repo_list(repo_data_path: str) -> List[ProtectionGroup]:
    data_path = Path(repo_data_path)
    if not data_path.exists:
        print('repo data file does not exist')
        return
    repo_data = []
    # Deal with extra columns
    with open(data_path, 'r') as csvfile:
        csv_reader = csv.DictReader(csvfile)
        for row in csv_reader:
            data_row = ProtectionGroup.from_dict(row)
            repo_data.append(data_row)
    return repo_data


def main(
    owner: str = "pcdshub",
    repo_name: str = "",
    repo_type: str = "Python Library",
    prot_master: bool = False,
    prot_pages: bool = False,
    prot_default: bool = False,
    repo_data_path: str = "",
    write: bool = False
):
    if repo_data_path:
        # run for each repo in list
        repo_data = parse_repo_list(repo_data_path)
        for protection_group in repo_data:
            protection_group.apply_protections(write=write)
        return

    if not repo_name:
        return

    # apply settings for a single repo
    protection_group = ProtectionGroup(
        owner=owner, repo_name=repo_name, repo_type=repo_type,
        master=prot_master, gh_pages=prot_pages, default=prot_default
    )
    protection_group.apply_protections(write=write)

    return


def _create_argparser() -> argparse.ArgumentParser:
    """
    Create an ArgumentParser for update_branch_protections

    Returns
    -------
    argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser()
    # specify an owner, repo, and settings
    parser.add_argument("owner", type=str, default='pcdshub', nargs='?')
    parser.add_argument("repo_name", type=str, default='', nargs='?')
    parser.add_argument("repo_type", type=str, default='Other', nargs='?')
    parser.add_argument("--protect-master", action="store_true", dest='prot_master')
    parser.add_argument("--protect-pages", action="store_true", dest='prot_pages')
    parser.add_argument("--protect-default", action="store_true", dest='prot_default')

    # Optionally specify everything at once
    parser.add_argument("--repo-data-path", type=str, dest='repo_data_path',
                        help='Path to repo data csv.  Expects columns for: '
                             '[orgname, reponame, apply_master, apply_pages, '
                             'apply_default]')

    parser.add_argument("--write", action="store_true", dest="write")

    return parser


def _main(args=None):
    """CLI entrypoint."""
    parser = _create_argparser()
    return main(**vars(parser.parse_args(args=args)))


if __name__ == "__main__":
    _main()
