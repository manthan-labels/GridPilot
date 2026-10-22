"""Pure simulation entry point, independent of UI and model providers."""
from .config import Config
from .profiles import make_profiles
from .scenarios import apply_scenario
from .controllers.rule_based import dispatch
from .metrics import summarize


def run(config: Config) -> tuple[dict, dict[str, float], dict]:
    config.validate()
    profiles = apply_scenario(config, make_profiles(config))
    result = dispatch(config, profiles)
    return result, summarize(result, config), profiles
