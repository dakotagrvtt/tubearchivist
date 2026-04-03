"""Django AppConfig for fork_features.

Adding ``fork_features`` to Django's INSTALLED_APPS causes this AppConfig to
be loaded, which imports each feature subpackage so its ``register()`` call
runs at startup — before any request is processed.

To add a new fork feature, import it here in ``ready()``.
"""

from django.apps import AppConfig


class ForkFeaturesConfig(AppConfig):
    name = "fork_features"
    verbose_name = "Fork Features"

    def ready(self) -> None:  # noqa: D401
        """Import all fork-feature subpackages to trigger registration."""
        # Each import below runs the top-level ``register()`` call inside
        # that feature's __init__.py.  Add a new line here for each feature.

        import fork_features.audio_tracks  # noqa: F401
        import fork_features.generic_downloads  # noqa: F401
