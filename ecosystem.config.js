module.exports = {
  apps : [{
    name: 'qdrant-sentinel',
    script: 'sentinel.py',
    // We point directly to the python executable created by uv
    interpreter: './.venv/Scripts/python.exe',
    env: {
      PYTHONUNBUFFERED: '1',
      OPEN_VIKING_ENABLED: 'true',
      // OPEN_VIKING_PATH: './bin/openviking-server' // Uncomment if openviking-server is not in system PATH
    }
  }]
};
