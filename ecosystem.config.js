module.exports = {
  apps : [{
    name: 'qdrant-sentinel',
    script: 'sentinel.py',
    // We point directly to the python executable created by uv
    interpreter: './.venv/Scripts/python.exe',
    env: {
      PYTHONUNBUFFERED: '1'
    }
  }]
};
