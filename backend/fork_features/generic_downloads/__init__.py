"""generic_downloads – download queued items with stored source URLs."""

from fork_features.registry import register

from .channel_enricher import GenericChannelFallbackEnricher
from .downloader import GenericDownloadHook

register(
    feature_id="generic_downloads",
    download_hook=GenericDownloadHook(),
    channel_fallback_enricher=GenericChannelFallbackEnricher(),
)
