module.exports = {
  apps : [
    {
      name: 'qdrant-sentinel',
      script: 'sentinel.py',
      // We point directly to the python executable created by uv
      interpreter: './.venv/Scripts/python.exe',
      env: {
        PYTHONUNBUFFERED: '1',
        OPEN_VIKING_ENABLED: 'true',
      }
    },
    {
      name: 'openviking-server',
      script: './.venv/Scripts/openviking-server.exe',
      args: '--host 127.0.0.1 --port 1933 --config C:/Users/pawel/.openviking/ov.conf',
      env: {
        PYTHONUNBUFFERED: '1'
      }
    }
  ]
};
