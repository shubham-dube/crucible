"""Built-in lint rules. Importing this package registers them in ``registry``."""

from crucible.topology.rules import safety, semantics, structure
from crucible.topology.rules.base import LintConfig, LintRule, RuleRegistry, registry

__all__ = ["LintConfig", "LintRule", "RuleRegistry", "registry", "safety", "semantics", "structure"]
