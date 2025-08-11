from sqlalchemy.orm import Session
from league.league_schema import Agent, AgentInstance
from league.init_db import get_default_db_path
from sqlalchemy import create_engine

# Connect
engine = create_engine(get_default_db_path())
session = Session(engine)

# Delete all rows from Agent
session.query(Agent).delete()
session.commit()

# delete all rows from AgentInstance table
session.query(AgentInstance).delete()
session.commit()

print("✅ Cleared all rows from Agent table.")

session.close()
