#!/bin/bash
# Start script for the mention dispatcher Railway service.
# Install agent_sdk from auto_feature_engineer, then run the dispatcher.
pip install "afe-scheduler @ git+https://github.com/rllm-org/auto_feature_engineer.git" -q
pip install psycopg[binary] httpx -q
python examples/mention_dispatcher.py
