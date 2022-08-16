"""Dynamic generation of gitlab CICD pipeline YAML files."""

from dataclasses import dataclass, field
from pathlib import Path
import os
from abc import abstractmethod, ABC
import enum

# from abc import
from typing import List, Iterable, Dict, Any, Optional

import yaml
from typer import Typer

app = Typer()

PATH_OUTPUT = Path(
    os.environ.get("PATH_OUTPUT_CICD_PYTHON", "cicd_generated.gitlab-ci.yml")
)


# @dataclass
# class Pipeline:
#     pass





class CICDElement(ABC):
    """An element present in a gitlab cicd pipeline configuration."""

    @abstractmethod
    def to_dict(self) -> Dict:
        """Return valid Gitlab CICD dict representation for yaml output."""

@dataclass
class Rule(CICDElement):

    if_: Optional[str] = None
    changes: Optional[List[str]] = None
    when: str = "on_success"
    exists: Optional[List[str]] = None
    allow_failure: bool = False



    IS_MERGE_REQUEST = {
        "if": "$CI_MERGE_REQUEST_ID"
    }
    IS_COMMIT_TO_DEFAULT_BRANCH = {
        "if": "$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH"
    }

    def to_dict(self) -> Dict:
        return self.value


RULE_IS_MERGE_REQUEST = Rule(if_="$CI_MERGE_REQUEST_ID")
RULE_IS_COMMIT_TO_DEFAULT_BRANCH = Rule(if_="$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH")

@dataclass
class Job(CICDElement):
    name: str
    image: Optional[str] = None

    description: Optional[str] = None

    before_script: List[str] = field(default_factory=list)
    script: List[str] = field(default_factory=list)
    after_script: List[str] = field(default_factory=list)

    variables: Dict[str, Any] = field(default_factory=dict)

    interruptible: Optional[bool] = False

    artifacts: List[str] = field(default_factory=list)

    # _list_need_job: List["Job"] = field(default_factory=list)
    _list_need: List["JobNeed"] = field(default_factory=list)

    def add_need(self, other: "Job", optional: bool = False) -> "JobNeed":
        """Add other as a need (dependency) to this job."""
        if not isinstance(other, self.__class__):
            raise TypeError(
                f"Other must be of type {self.__class__} (was of type {other.__class__})."
            )

        job_need = JobNeed(job_dependency=other, optional=optional)

        self._list_need.append(job_need)
        return job_need

    def __rshift__(self, other: "Job"):
        if isinstance(other, Iterable):
            for other_item in other:
                self.add_need(other_item)

        self.add_need(other)

    def to_dict(self) -> Dict:
        return dict(
            before_script=self.before_script,
            script=self.script,
            after_script=self.after_script,
            needs=[job_need.to_dict() for job_need in self._list_need],
            interruptible=self.interruptible,
        )


@dataclass
class JobNeed(CICDElement):
    job_dependency: Job
    optional: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"job": self.job_dependency.name, "optional": self.optional}


@dataclass
class Stage(CICDElement):
    """Gitlab CICD stage for one or more jobs."""

    name: str
    list_job: List[Job] = field(default_factory=list)

    variables: Dict[str, Any] = field(default_factory=dict)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass

    def to_dict(self) -> Dict:
        raise ValueError(
            f"A {self.__class__.__name__} cannot be directly transformed to a dict."
        )

    def get_dict_jobs(self) -> Dict:
        return {
            job.name: {**job.to_dict(), "stage": self.name} for job in self.list_job
        }

    def add(self, job: Job):
        self.list_job.append(job)
        return job


@dataclass
class Pipeline(CICDElement):
    """A pipeline which contains one or more stages."""

    list_stage: List[Stage] = field(default_factory=list)

    defaults: Dict[str, Any] = field(default_factory=lambda: {"tags": ["k8s-standard"]})

    variables: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        dict_jobs = {}
        for stage in self.list_stage:
            dict_jobs.update(stage.get_dict_jobs())

        return {
            "defaults": self.defaults,
            "stages": [stage.name for stage in self.list_stage],
            # **{
            #     job_name: job_dict
            #     for job_name, job_dict in sum((stage.get_dict_jobs() for stage in self.list_stage), start={}).items()
            # }
            **dict_jobs,
        }

    def add(self, stage: Stage):
        self.list_stage.append(stage)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        pass


if __name__ == "__main__":

    pipeline = Pipeline()

    stage_prep = Stage(
        name="prep",
    )

    pipeline.add(stage_prep)

    job_docker_lint = Job(
        name="docker-lint-dockerfile",
        image="hadolint/hadolint:${HADOLINT_VERSION}-debian",
        script=["hadolint ${DOCKERFILE_FILE}"],
        interruptible=True,
    )
    job_python_freeze_requirements = Job(
        name="python-freeze-requirements",
        image="python:3.8",
        script=[
            "python --version",
            "pip --version",
            "pip install -c constraints.txt -r requirements.txt",
            "pip freeze > ${PATH_REQUIREMENTS_PYTHON_FROZEN}",
        ],
        artifacts=["${PATH_REQUIREMENTS_PYTHON_FROZEN}"],
    )

    stage_prep.add(job_docker_lint)
    stage_prep.add(job_python_freeze_requirements)

    for path in Path().iterdir():
        if not path.is_dir() or not path.name.endswith("_pipeline"):
            continue

    with PATH_OUTPUT.open("w", encoding="utf-8") as file:
        yaml.dump(
            pipeline.to_dict(), file, default_flow_style=False, default_style=False
        )
