let
    Rows = OperationsSnapshot[fact_review_history],
    Data = Table.FromRecords(Rows, {"request_id", "review_id", "action", "previous_action", "reason", "actor", "owner", "created_at", "port_id", "week_start", "risk_level", "run_id", "classification", "lineage_id", "risk_revision", "version"}, MissingField.UseNull),
    Typed = Table.TransformColumnTypes(Data, {{"request_id", type text}, {"review_id", type text}, {"action", type text}, {"previous_action", type text}, {"reason", type text}, {"actor", type text}, {"owner", type text}, {"created_at", type text}, {"port_id", type text}, {"week_start", type text}, {"risk_level", type text}, {"run_id", type text}, {"classification", type text}, {"lineage_id", type text}, {"risk_revision", type text}, {"version", Int64.Type}})
in
    Typed
