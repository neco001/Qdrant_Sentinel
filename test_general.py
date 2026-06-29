from sentinel import get_status_report, get_qdrant_client, get_db_connection
qdrant = get_qdrant_client()
conn = get_db_connection()
print(get_status_report(qdrant, conn))