# Distributed Search Engine

This repository will contain each stage of a distributed search engine as a separate component.

`ingestion_crawler/` currently implements the first stage: controlled acquisition and preservation of raw public HTML. Its output is intentionally shared through `data/`, so future parser, indexing, sharding, and service components can consume it without depending on crawler internals.
