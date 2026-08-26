CREATE CONSTRAINT entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.id IS UNIQUE;

MATCH (n) DETACH DELETE n;

LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
MERGE (n:Entity {id: row.id})
SET n.type = row.type,
    n.name = row.name,
    n.release_year = CASE row.release_year WHEN '' THEN null ELSE toInteger(row.release_year) END
FOREACH (_ IN CASE WHEN row.type = 'User' THEN [1] ELSE [] END | SET n:User)
FOREACH (_ IN CASE WHEN row.type = 'Game' THEN [1] ELSE [] END | SET n:Game)
FOREACH (_ IN CASE WHEN row.type = 'Genre' THEN [1] ELSE [] END | SET n:Genre)
FOREACH (_ IN CASE WHEN row.type = 'Platform' THEN [1] ELSE [] END | SET n:Platform)
FOREACH (_ IN CASE WHEN row.type = 'Franchise' THEN [1] ELSE [] END | SET n:Franchise);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
WITH row WHERE row.type = 'HAS_GENRE'
MATCH (source:Game {id: row.source})
MATCH (target:Genre {id: row.target})
MERGE (source)-[:HAS_GENRE]->(target);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
WITH row WHERE row.type = 'AVAILABLE_ON'
MATCH (source:Game {id: row.source})
MATCH (target:Platform {id: row.target})
MERGE (source)-[:AVAILABLE_ON]->(target);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
WITH row WHERE row.type = 'PART_OF_FRANCHISE'
MATCH (source:Game {id: row.source})
MATCH (target:Franchise {id: row.target})
MERGE (source)-[:PART_OF_FRANCHISE]->(target);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
WITH row WHERE row.type = 'RELATED_TO'
MATCH (source:Game {id: row.source})
MATCH (target:Game {id: row.target})
MERGE (source)-[:RELATED_TO]->(target);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
WITH row WHERE row.type = 'OWNS_PLATFORM'
MATCH (source:User {id: row.source})
MATCH (target:Platform {id: row.target})
MERGE (source)-[:OWNS_PLATFORM]->(target);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
WITH row WHERE row.type = 'PREFERS_GENRE'
MATCH (source:User {id: row.source})
MATCH (target:Genre {id: row.target})
MERGE (source)-[:PREFERS_GENRE]->(target);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
WITH row WHERE row.type = 'PLAYED'
MATCH (source:User {id: row.source})
MATCH (target:Game {id: row.target})
MERGE (source)-[:PLAYED]->(target);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
WITH row WHERE row.type = 'LIKES'
MATCH (source:User {id: row.source})
MATCH (target:Game {id: row.target})
MERGE (source)-[:LIKES]->(target);

LOAD CSV WITH HEADERS FROM 'file:///relationships.csv' AS row
WITH row WHERE row.type = 'DISLIKES'
MATCH (source:User {id: row.source})
MATCH (target:Game {id: row.target})
MERGE (source)-[:DISLIKES]->(target);
