from __future__ import annotations

import collections
import dataclasses
import functools
import json
import pathlib
import subprocess
from dataclasses import field
from typing import Any, Generic, TypeVar, Union

import apischema
from apischema.metadata import alias

script_path = pathlib.Path(__file__).resolve().parent


default_required_status_checks = [
    "standard / Conda (3.10) / Python 3.10: conda",
    "standard / Conda (3.9, true) / Python 3.9: conda",
    "standard / Documentation / Python 3.9: documentation building",
    "standard / Pip (3.10) / Python 3.10: pip",
    "standard / Pip (3.9, true) / Python 3.9: pip",
    "standard / pre-commit checks / pre-commit",
]


@functools.lru_cache()
def get_packaged_graphql(filename: str) -> str:
    # Ref: https://graphql.org/learn/queries/
    # Ref: https://gist.github.com/duboisf/68fb6e22ac0a2165ca298074f0e3b553

    with open(script_path / "graphql" / filename, "rt") as fp:
        return fp.read().strip()


def run_gh(*command: str) -> bytes:
    return subprocess.check_output(["gh", *command])


def gh_api(*command: str, hostname: str = "github.com") -> dict:
    raw_json = run_gh("api", "--hostname", hostname, *command)
    return json.loads(raw_json)


def gh_api_graphql(
    query: str,
    hostname: str = "github.com",
    **params: list[str] | str | bool | int,
) -> dict:

    args = []

    def find_params():
        yield "query", query
        for name, value in params.items():
            if isinstance(value, list):
                for item in value:
                    yield f"{name}[]", item
            else:
                yield name, value

    for name, value in find_params():
        if isinstance(value, str):
            value = value.replace("'", r"\'")
            # -f is a raw field - a string parameter
            args.extend(["-f", f"{name}={value}"])
        elif isinstance(value, bool):
            value = "true" if value else "false"
            args.extend(["-F", f"{name}={value}"])
        else:
            # -F is a typed field
            args.extend(["-F", f"{name}={value!r}"])

    raw_json = run_gh("api", "graphql", "--hostname", hostname, *args)
    return json.loads(raw_json)


def gh_graphql_describe(type_: str):
    return gh_api_graphql(query='''\
        query {
          __type(name: "''' + type_ + '''") {
            name
            kind
            description
            fields {
                name
                type {
                    name
                    kind
                    ofType {
                        name
                        kind
                    }
                }
                description
            }
          }
        }
''')


class Serializable:
    @classmethod
    def from_dict(cls, info: dict[str, Any]):
        return apischema.deserialize(cls, info)


@dataclasses.dataclass
class Actor(Serializable):
    login: str = ""


@dataclasses.dataclass
class BranchProtection(Serializable):
    creator: Actor = field(default_factory=Actor)
    id: str = ""

    allows_deletions: bool = field(default=False, metadata=alias("allowsDeletions"))
    allows_force_pushes: bool = field(
        default=False, metadata=alias("allowsForcePushes")
    )
    is_admin_enforced: bool = field(default=False, metadata=alias("isAdminEnforced"))
    required_status_checks: list[str] = field(
        default_factory=default_required_status_checks.copy,
        metadata=alias("requiredStatusCheckContexts"),
    )
    required_approving_review_count: int = field(
        default=1, metadata=alias("requiredApprovingReviewCount")
    )
    requires_approving_reviews: bool = field(
        default=True, metadata=alias("requiresApprovingReviews")
    )
    requires_code_owner_reviews: bool = field(
        default=False, metadata=alias("requiresCodeOwnerReviews")
    )
    requires_status_checks: bool = field(
        default=True, metadata=alias("requiresStatusChecks")
    )
    restricts_pushes: bool = field(default=True, metadata=alias("restrictsPushes"))
    restricts_review_dismissals: bool = field(
        default=False, metadata=alias("restrictsReviewDismissals")
    )
    dismisses_stale_reviews: bool = field(
        default=False, metadata=alias("dismissesStaleReviews")
    )
    pattern: str = field(default="master")

    def create(self, repo: Repository) -> BranchProtection:
        info = gh_api_graphql(
            get_packaged_graphql("branch_protection.graphql"),
            operationName="addBranchProtection",
            repositoryId=repo.id,
            requiredStatusChecks=self.required_status_checks,
            allowsDeletions=self.allows_deletions,
            allowsForcePushes=self.allows_force_pushes,
            dismissesStaleReviews=self.dismisses_stale_reviews,
            isAdminEnforced=self.is_admin_enforced,
            requiresApprovingReviews=self.requires_approving_reviews,
            requiredApprovingReviewCount=self.required_approving_review_count,
            requiresCodeOwnerReviews=self.requires_code_owner_reviews,
            requiresStatusChecks=self.requires_status_checks,
            restrictsReviewDismissals=self.restricts_review_dismissals,
            branchPattern=self.pattern,
        )
        return self.from_dict(
            info["data"]["createBranchProtectionRule"]["branchProtectionRule"]
        )

    def delete(self) -> str:
        info = gh_api_graphql(
            get_packaged_graphql("branch_protection.graphql"),
            operationName="deleteBranchProtection",
            ruleId=self.id,
        )
        return info["data"]["deleteBranchProtectionRule"]["clientMutationId"]

    @classmethod
    def from_repository(cls, repo: Repository) -> list[BranchProtection]:
        info = gh_api_graphql(
            get_packaged_graphql("branch_protection.graphql"),
            operationName="showBranchProtection",
            owner=repo.owner,
            repo=repo.repo,
        )["data"]["repository"]
        return [
            cls.from_dict(node)
            for node in info["branchProtectionRules"].get("nodes", [])
        ]


T = TypeVar("T")


@dataclasses.dataclass
class NodeList(collections.UserList, Generic[T]):
    nodes: list[T]

    @property
    def data(self):
        return self.nodes

    def __str__(self):
        return repr(self.data)

    def __repr__(self):
        return repr(self.data)


@dataclasses.dataclass
class User(Serializable):
    login: str
    name: str


@dataclasses.dataclass
class Team(Serializable):
    combined_slug: str = field(metadata=alias("combinedSlug"))


@dataclasses.dataclass
class ProtectionRule(Serializable):
    timeout: int
    reviewers: NodeList[Union[User, Team]]


@dataclasses.dataclass
class Environment(Serializable):
    id: str
    name: str
    protectionRules: NodeList[ProtectionRule]


@dataclasses.dataclass
class Repository(Serializable):
    id: str
    name: str
    description: str
    environments: NodeList[Environment]
    full_name: str = field(metadata=alias("nameWithOwner"))
    homepage_url: str = field(metadata=alias("homepageUrl"))

    @property
    def owner(self) -> str:
        return self.full_name.split("/", 1)[0]

    @property
    def repo(self) -> str:
        return self.full_name.split("/", 1)[1]

    @classmethod
    def from_name(
        cls, owner: str, repo: str, hostname: str = "github.com"
    ) -> Repository:
        info = gh_api_graphql(
            get_packaged_graphql("repository_info.graphql"),
            hostname=hostname,
            operationName="showRepositoryInfo",
            owner=owner,
            repo=repo,
        )["data"]["repository"]
        print(json.dumps(info, indent=2))
        return cls.from_dict(info)

    def create_environment(self, name: str):
        data = gh_api_graphql(
            get_packaged_graphql("repository_info.graphql"),
            operationName="createEnvironment",
            repositoryId=self.id,
            name=name,
        )["data"]
        env = data["createEnvironment"]["environment"]
        return Environment.from_dict(env)


def main(owner: str, repo_name: str):
    repo = Repository.from_name(owner=owner, repo=repo_name)
    print("Creating environment gh-pages")
    repo.create_environment("gh-pages")

    print("Repository:", repo)
    for prot in BranchProtection.from_repository(repo):
        print("Deleting branch protection setting")
        prot.delete()
    prot = BranchProtection()
    new_rule = prot.create(repo)
    print("Created rule")
    print(new_rule)


if __name__ == "__main__":
    main("pcdshub", "pcds-ci-test-repo-python")
    # info = gh_graphql_describe("Environment")
    # print(json.dumps(info, indent=2))
