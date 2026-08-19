# Collector 1.0 Core contract

`core.intel_contracts` is the stable dependency boundary shared by the daily
briefing aggregator and independently installable intelligence sources.
Source packages may depend on this package; Core never imports a source package,
and source packages must not import `features.daily_briefing` internals.

The frozen public exports are:

- data: `CollectRequest`, `CollectorResult`, `IntelItem`, `SourceCoverage`
- enums and identifiers: `CacheStatus`, `CoverageStatus`,
  `COLLECTOR_CONTRACT_VERSION`, `PUBLIC_SOURCE_IDS`, `PUBLIC_SOURCE_ID_SET`
- protocols: `Collector`, `CollectorGateway`, `ObservableCollectorGateway`,
  `CollectorProgressCallback`
- registry: `CollectorRegistry`
- normalization and validation: `normalize_source_ids`, `normalize_url`,
  `sanitize_external_text`, `json_safe_mapping`, `stable_item_id`,
  `aware_timestamp`, `rfc3339`, `get_timezone`, `localize`,
  `ensure_compatible_contract`, `is_valid_source_id`

The contract version is `1.0`. Readers accept unknown object keys within the
same major version and reject an incompatible major version. Required fields,
the eight public source IDs, timezone-aware timestamp rules, stable-ID rules,
URL normalization and secret filtering retain their Collector 1.0 semantics.

`features.daily_briefing.models`, `collector_contracts` and `time_utils` are
compatibility re-exports. They preserve Python type identity for existing
consumers but are not valid dependencies for new source packages.

`CollectorRegistry` is process-local and thread-safe. Optional source modules
register one Collector per public `source_id`; an absent source is represented
by the aggregator as `not_configured`, without preventing other sources from
running. Registry contents, collection results and source configuration are not
persisted by this Core package.
