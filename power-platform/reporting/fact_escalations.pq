let
    Rows = OperationsSnapshot[fact_escalations],
    Data = Table.FromRecords(Rows, {"event_id", "review_id", "port_id", "port_name", "week_start", "risk_level", "previous_risk", "risk_revision", "source_latest_observation", "freshness_status", "created_at", "review_reference", "run_id", "classification", "lineage_id", "delivery_status", "last_attempt_at", "last_failure_reason", "attempts", "unresolved_exception", "simulated"}, MissingField.UseNull),
    Typed = Table.TransformColumnTypes(Data, {{"event_id", type text}, {"review_id", type text}, {"port_id", type text}, {"port_name", type text}, {"week_start", type text}, {"risk_level", type text}, {"previous_risk", type text}, {"risk_revision", type text}, {"source_latest_observation", type text}, {"freshness_status", type text}, {"created_at", type text}, {"review_reference", type text}, {"run_id", type text}, {"classification", type text}, {"lineage_id", type text}, {"delivery_status", type text}, {"last_attempt_at", type text}, {"last_failure_reason", type text}, {"attempts", Int64.Type}, {"unresolved_exception", type logical}, {"simulated", type logical}})
in
    Typed
