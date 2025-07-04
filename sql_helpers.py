import os
import logging
from typing import Dict, Any, Optional, List, Union, Tuple
from sqlalchemy import create_engine, MetaData, select, text, func
from sqlalchemy.exc import SQLAlchemyError

# Setup logging
logger = logging.getLogger(__name__)

# JSON paths inside insights.profile (PostgreSQL JSONB operators)
METRIC_PATHS = {
    "tam": "market -> 'data' ->> 'tam'",
    "arr": "profile -> 'data' -> 'financials' -> 'revenue' ->> 'recent'",
    "nrr": "profile -> 'data' -> 'financials' -> 'revenue' ->> 'nrr'",
    "burn": "profile -> 'data' -> 'financials' -> 'cash_flow' ->> 'burn_rate'",
    "runway": "profile -> 'data' -> 'financials' -> 'cash_flow' ->> 'runway_months'",
    "revenue": "profile -> 'data' -> 'financials' -> 'revenue' ->> 'recent'",
    "valuation": "profile -> 'data' -> 'financials' -> 'valuation' ->> 'current'",
    "funding": "profile -> 'data' -> 'financials' -> 'funding' ->> 'total_funding'",
    "employees": "profile -> 'data' -> 'company_info' ->> 'employee_count'",
    "growth_rate": "profile -> 'data' -> 'financials' -> 'revenue' ->> 'growth_rate'",
    # New comprehensive paths for all requested metrics
    "latest_funding_amount": "profile -> 'data' -> 'financials' -> 'funding' -> 'rounds' -> -1 ->> 'amount'",
    "total_funding": "profile -> 'data' -> 'financials' -> 'funding' ->> 'total_funding'",
    "orbe_valuation": "market -> 'data' ->> 'valuation'",
    "cac": "profile -> 'data' -> 'financials' -> 'metrics' ->> 'cac'",
    "ltv": "profile -> 'data' -> 'financials' -> 'metrics' ->> 'ltv'",
    "funding_ask": "profile -> 'data' -> 'financials' -> 'funding' -> 'future_plans' -> 0 ->> 'target_amount'"
    # Always use ->> (text) then cast to numeric later
    # Bot logic relies on these keys being lowercase
}

# Database configuration
DB_HOST = os.getenv("DB_HOST", "orbe360.ai")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Admin0rbE")
DB_NAME = os.getenv("DB_NAME", "orbe_dev")

DB_CONNECTION_STRING = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def get_db_engine():
    """Get a SQLAlchemy engine for database connections"""
    try:
        engine = create_engine(
            DB_CONNECTION_STRING,
            connect_args={
                "connect_timeout": 10,
                "application_name": "OrbeSQL"
            },
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            pool_pre_ping=True
        )
        return engine
    except Exception as e:
        logger.error(f"Error creating database engine: {e}")
        raise

def metric_by_investor(metric: str, investor_id: str, agg: Optional[str] = None):
    """
    Fetch a metric (e.g., TAM, ARR) for every deal owned by `investor_id`,
    or return an aggregate if `agg` is 'max', 'sum', or 'avg'.

    Parameters
    ----------
    metric       one of METRIC_PATHS keys, case-insensitive
    investor_id  UUID string of investor
    agg          None | 'max' | 'sum' | 'avg'

    Returns
    -------
    list[Row] or Row | None
    """
    try:
        metric = metric.lower()
        if metric not in METRIC_PATHS:
            raise ValueError(f"Unknown metric '{metric}'. "
                           f"Valid: {', '.join(METRIC_PATHS)}")

        # Safe JSON selector
        selector = f"({METRIC_PATHS[metric]})::NUMERIC"

        if agg:
            if agg.lower() not in ("max", "sum", "avg"):
                raise ValueError("agg must be max, sum, avg or None")
            sql_select = f"{agg.upper()}({selector}) AS value"
            sql_group = ""
            sql_order = ""
        else:
            # Per-company list
            sql_select = f"c.name AS company, d.id AS deal_id, {selector} AS value"
            sql_group = "GROUP BY c.name, d.id, value"
            sql_order = "ORDER BY value DESC NULLS LAST"

        # Build the WHERE clause to handle null values properly
        json_path = METRIC_PATHS[metric]
        
        stmt = text(f"""
            SELECT {sql_select}
            FROM   insights  i
            JOIN   deals     d ON d.id::text = i."dealId"::text
            JOIN   companies c ON c.id::text = d."startupId"::text
            WHERE  d."investorId"::text = :inv
              AND  {json_path} IS NOT NULL
              AND  {json_path} != 'null'
              AND  {json_path} != ''
              AND  {json_path} ~ '^[0-9]+\.?[0-9]*$'
            {sql_group}
            {sql_order}
        """)

        engine = get_db_engine()
        with engine.connect() as conn:
            result = conn.execute(stmt, {"inv": investor_id})
            if agg:
                row = result.fetchone()
                return row if row else None
            else:
                rows = result.fetchall()
                return rows if rows else []
                
    except ValueError as e:
        logger.error(f"Invalid parameter in metric_by_investor: {e}")
        raise
    except Exception as e:
        logger.error(f"Error in metric_by_investor: {e}")
        return None if agg else []

def detect_aggregation_query(query: str) -> bool:
    """Detect if a query is asking for aggregation (count, sum, average, etc.)"""
    import re
    
    # Word boundary patterns for single words to avoid false positives
    word_boundary_keywords = ['count', 'sum', 'total', 'average', 'avg', 'max', 'min', 'statistics', 'stats', 'aggregate', 'highest', 'lowest', 'largest', 'smallest', 'biggest', 'rank', 'ranking', 'top', 'bottom', 'best', 'worst']
    
    # Multi-word phrases that can use substring matching
    phrase_keywords = [
        'how many', 'number of', 'total number', 'how much',
        'which deals', 'which companies', 'compare deals', 'compare companies',
        'all my deals', 'my portfolio', 'portfolio companies',
        'show me all', 'list all', 'all companies'
    ]
    
    query_lower = query.lower()
    
    # Check word boundary keywords
    for keyword in word_boundary_keywords:
        if re.search(r'\b' + re.escape(keyword) + r'\b', query_lower):
            return True
    
    # Check phrase keywords
    for phrase in phrase_keywords:
        if phrase in query_lower:
            return True
    
    return False

def execute_count_query(table_name: str, filters: Dict[str, Any] = None) -> Optional[int]:
    """Execute a count query on a specific table with optional filters"""
    try:
        engine = get_db_engine()
        metadata = MetaData()
        metadata.reflect(bind=engine)
        
        if table_name not in metadata.tables:
            logger.warning(f"Table {table_name} not found")
            return None
            
        table = metadata.tables[table_name]
        
        # Build count query
        stmt = select(func.count()).select_from(table)
        
        # Apply filters if provided
        if filters:
            for column_name, value in filters.items():
                if column_name in [col.name for col in table.columns]:
                    column = table.c[column_name]
                    if isinstance(value, list):
                        stmt = stmt.where(column.in_(value))
                    else:
                        stmt = stmt.where(column == value)
        
        with engine.connect() as conn:
            result = conn.execute(stmt)
            count = result.scalar()
            return count
            
    except SQLAlchemyError as e:
        logger.error(f"SQL error in count query: {e}")
        return None
    except Exception as e:
        logger.error(f"Error executing count query: {e}")
        return None

def get_table_statistics() -> Dict[str, Any]:
    """Get basic statistics for all important tables"""
    try:
        engine = get_db_engine()
        metadata = MetaData()
        metadata.reflect(bind=engine)
        
        stats = {}
        important_tables = ['deals', 'companies', 'company_markets', 'insights', 'users', 'data_rooms']
        
        for table_name in important_tables:
            if table_name in metadata.tables:
                table = metadata.tables[table_name]
                
                with engine.connect() as conn:
                    # Get total count
                    count_stmt = select(func.count()).select_from(table)
                    total_count = conn.execute(count_stmt).scalar()
                    
                    table_stats = {
                        'total_count': total_count,
                        'columns': [col.name for col in table.columns]
                    }
                    
                    # Get some additional stats for specific tables
                    if table_name == 'deals':
                        # Count by status
                        status_stmt = select(table.c.status, func.count()).group_by(table.c.status)
                        status_results = conn.execute(status_stmt).fetchall()
                        table_stats['by_status'] = {row[0]: row[1] for row in status_results}
                        
                    elif table_name == 'companies':
                        # Count by role
                        role_stmt = select(table.c.role, func.count()).group_by(table.c.role)
                        role_results = conn.execute(role_stmt).fetchall()
                        table_stats['by_role'] = {row[0]: row[1] for row in role_results}
                    
                    stats[table_name] = table_stats
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting table statistics: {e}")
        return {}

def maybe_metric_query(msg: str) -> Optional[tuple]:
    """Detect if a message is asking for metric data and return (metric, agg) tuple"""
    q = msg.lower()
    
    # Highest/Max patterns
    if any(pattern in q for pattern in ["highest tam", "max tam", "largest tam", "biggest tam"]):
        return ("tam", "max")
    if any(pattern in q for pattern in ["highest arr", "max arr", "largest arr"]):
        return ("arr", "max")
    if any(pattern in q for pattern in ["highest revenue", "max revenue", "largest revenue"]):
        return ("revenue", "max")
    if any(pattern in q for pattern in ["highest valuation", "max valuation", "largest valuation"]):
        return ("valuation", "max")
    
    # Sum/Total patterns
    if any(pattern in q for pattern in ["total tam", "sum tam", "sum of tam"]):
        return ("tam", "sum")
    if any(pattern in q for pattern in ["total arr", "sum arr", "sum of arr"]):
        return ("arr", "sum")
    if any(pattern in q for pattern in ["total revenue", "sum revenue", "sum of revenue"]):
        return ("revenue", "sum")
    
    # Average patterns
    if any(pattern in q for pattern in ["average tam", "avg tam", "mean tam"]):
        return ("tam", "avg")
    if any(pattern in q for pattern in ["average arr", "avg arr", "mean arr"]):
        return ("arr", "avg")
    
    # List/Show all patterns
    if any(pattern in q for pattern in ["list tam", "tam for all", "show tam", "all tam"]):
        return ("tam", None)
    if any(pattern in q for pattern in ["list arr", "arr for all", "show arr", "all arr"]):
        return ("arr", None)
    if any(pattern in q for pattern in ["list revenue", "revenue for all", "show revenue", "all revenue"]):
        return ("revenue", None)
    if any(pattern in q for pattern in ["list valuation", "valuation for all", "show valuation", "all valuation"]):
        return ("valuation", None)
    
    # Portfolio/deals patterns
    if any(pattern in q for pattern in ["portfolio tam", "my deals tam", "deals tam"]):
        return ("tam", None)
    if any(pattern in q for pattern in ["portfolio companies", "my companies", "my portfolio"]) and "tam" in q:
        return ("tam", None)
    
    return None

def execute_custom_aggregation(query_text: str, investor_id: str = None) -> Optional[Dict[str, Any]]:
    """Execute a custom aggregation query based on natural language"""
    try:
        # First check if this is a metric query
        if investor_id:
            metric_req = maybe_metric_query(query_text)
            if metric_req:
                metric, agg = metric_req
                logger.info('Inside metric query')
                try:
                    data = metric_by_investor(metric, investor_id, agg)
                    if data:
                        logger.info('Inside metric query data')
                        return {
                            'type': 'metric_query',
                            'metric': metric,
                            'agg': agg,
                            'result': data
                        }
                except Exception as e:
                    logger.error(f"Error in metric query: {e}")
        
        engine = get_db_engine()
        
        # Parse the query to determine what to aggregate
        query_lower = query_text.lower()
        
        # Simple query patterns
        if 'how many deals' in query_lower:
            count = execute_count_query('deals', filters={"investorId": investor_id})
            return {'type': 'count', 'table': 'deals', 'result': count}
            
        elif 'how many companies' in query_lower:
            count = execute_count_query('companies', filters={"investorId": investor_id})
            return {'type': 'count', 'table': 'companies', 'result': count}
            
        elif 'how many insights' in query_lower:
            count = execute_count_query('insights', filters={"investorId": investor_id})
            return {'type': 'count', 'table': 'insights', 'result': count}
            
        elif 'deals by status' in query_lower or 'deal status' in query_lower:
            stats = get_table_statistics()
            if 'deals' in stats and 'by_status' in stats['deals']:
                return {'type': 'group_count', 'table': 'deals', 'group_by': 'status', 'result': stats['deals']['by_status']}
                
        elif 'companies by role' in query_lower or 'company role' in query_lower:
            stats = get_table_statistics()
            if 'companies' in stats and 'by_role' in stats['companies']:
                return {'type': 'group_count', 'table': 'companies', 'group_by': 'role', 'result': stats['companies']['by_role']}
        
        # If no specific pattern matches, return general stats
        stats = get_table_statistics()
        return {'type': 'general_stats', 'result': stats}
        
    except Exception as e:
        logger.error(f"Error executing custom aggregation: {e}")
        return None

def format_aggregation_response(agg_result: Dict[str, Any]) -> str:
    """Format aggregation results into a human-readable response"""
    if not agg_result:
        return "I couldn't retrieve the requested statistics from the database."
    
    result_type = agg_result.get('type', 'unknown')
    
    if result_type == 'metric_query':
        metric = agg_result.get('metric', 'unknown')
        agg = agg_result.get('agg')
        result = agg_result.get('result')
        
        if not result:
            return f"No {metric.upper()} data found for your portfolio."
        
        if agg:
            # Aggregated result (single value)
            value = result.value if hasattr(result, 'value') else result[0]
            if value is None:
                return f"No {metric.upper()} data available for aggregation."
            
            # Format the value based on metric type
            if metric in ['tam', 'arr', 'revenue', 'valuation', 'funding']:
                formatted_value = f"${int(float(value)):,}"
            elif metric in ['runway']:
                formatted_value = f"{int(float(value))} months"
            elif metric in ['employees']:
                formatted_value = f"{int(float(value)):,} employees"
            elif metric in ['growth_rate', 'nrr']:
                formatted_value = f"{float(value):.1f}%"
            else:
                formatted_value = f"{float(value):,.2f}"
            
            return f"{agg.capitalize()} {metric.upper()} in your portfolio: {formatted_value}"
        else:
            # List of companies with values
            if not result:
                return f"No companies in your portfolio have {metric.upper()} data."
            
            response = f"{metric.upper()} for your portfolio companies:\n\n"
            for row in result:
                company = row.company if hasattr(row, 'company') else row[0]
                value = row.value if hasattr(row, 'value') else row[2]
                
                if metric in ['tam', 'arr', 'revenue', 'valuation', 'funding']:
                    formatted_value = f"${int(float(value)):,}"
                elif metric in ['runway']:
                    formatted_value = f"{int(float(value))} months"
                elif metric in ['employees']:
                    formatted_value = f"{int(float(value)):,} employees"
                elif metric in ['growth_rate', 'nrr']:
                    formatted_value = f"{float(value):.1f}%"
                else:
                    formatted_value = f"{float(value):,.2f}"
                
                response += f"• **{company}**: {formatted_value}\n"
            
            return response
    
    elif result_type == 'count':
        table = agg_result.get('table', 'unknown')
        count = agg_result.get('result', 0)
        return f"There are {count:,} records in the {table} table."
        
    elif result_type == 'group_count':
        table = agg_result.get('table', 'unknown')
        group_by = agg_result.get('group_by', 'unknown')
        result = agg_result.get('result', {})
        
        response = f"Here's the breakdown of {table} by {group_by}:\n"
        for key, count in result.items():
            response += f"- {key}: {count:,}\n"
        return response
        
    elif result_type == 'general_stats':
        result = agg_result.get('result', {})
        response = "Here are the current database statistics:\n\n"
        
        for table_name, stats in result.items():
            total = stats.get('total_count', 0)
            response += f"**{table_name.title()}**: {total:,} records\n"
            
            # Add specific breakdowns if available
            if 'by_status' in stats:
                response += "  Status breakdown:\n"
                for status, count in stats['by_status'].items():
                    response += f"    - {status}: {count:,}\n"
                    
            if 'by_role' in stats:
                response += "  Role breakdown:\n"
                for role, count in stats['by_role'].items():
                    response += f"    - {role}: {count:,}\n"
            
            response += "\n"
        
        return response
    
    return "Retrieved statistics from the database."

def search_deals_by_criteria(criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Search deals by specific criteria"""
    try:
        engine = get_db_engine()
        metadata = MetaData()
        metadata.reflect(bind=engine)
        
        if 'deals' not in metadata.tables:
            return []
            
        table = metadata.tables['deals']
        stmt = select(table)
        
        # Apply filters
        for key, value in criteria.items():
            if key in [col.name for col in table.columns]:
                column = table.c[key]
                if isinstance(value, list):
                    stmt = stmt.where(column.in_(value))
                else:
                    stmt = stmt.where(column == value)
        
        # Limit results
        stmt = stmt.limit(100)
        
        with engine.connect() as conn:
            result = conn.execute(stmt)
            rows = result.fetchall()
            
        return [dict(row._mapping) for row in rows]
        
    except Exception as e:
        logger.error(f"Error searching deals: {e}")
        return []

def query_tam_for_company(company_name: str, investor_id: str = None) -> Dict[str, Any]:
    """Query TAM (Total Addressable Market) for a specific company using JSONB - returns both Orbe estimate and company report"""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            # Query insights table for TAM data from both sources with optional investor filtering
            base_query = """
                SELECT 
                    i.market->'data'->>'tam' as orbe_tam,
                    i.profile->'data'->'market_and_industry'->>'total_addressable_market' as company_tam,
                    i.market->'data'->>'tam_source' as orbe_source,
                    c.name as company_name
                FROM insights i
                JOIN deals d ON i."dealId"::text = d.id::text
                JOIN companies c ON d."startupId"::text = c.id::text
                WHERE LOWER(c.name) LIKE LOWER(:company_name)
                AND (i.market->'data'->>'tam' IS NOT NULL OR i.profile->'data'->'market_and_industry'->>'total_addressable_market' IS NOT NULL)
            """
            
            params = {"company_name": f"%{company_name}%"}
            
            # Add investor filtering if provided
            if investor_id:
                base_query += " AND d.\"investorId\"::text = :investor_id"
                params["investor_id"] = investor_id
            
            base_query += " LIMIT 1"
            query = text(base_query)
            
            result = conn.execute(query, params)
            row = result.fetchone()
            
            if row:
                def safe_float(value):
                    try:
                        return float(value) if value and str(value).strip() and str(value) != '0' else None
                    except (ValueError, TypeError):
                        return None
                
                return {
                    "orbe_estimate": safe_float(row[0]),
                    "company_report": safe_float(row[1]),
                    "orbe_source": row[2] if row[2] else None,
                    "company_name": row[3]
                }
            return {}
    except Exception as e:
        logger.error(f"Error querying TAM for {company_name}: {e}")
        return {}

def query_contact_info_for_company(company_name: str, investor_id: str = None) -> Dict[str, Any]:
    """Query contact information for a specific company using JSONB"""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            # Query insights table for contact data with optional investor filtering
            base_query = """
                SELECT 
                    i.profile->'data'->'company'->'contact'->>'email' as email,
                    i.profile->'data'->'company'->'contact'->>'phone' as phone,
                    i.profile->'data'->'company'->>'website' as website,
                    c.name as company_name
                FROM insights i
                JOIN deals d ON i."dealId"::text = d.id::text
                JOIN companies c ON d."startupId"::text = c.id::text
                WHERE LOWER(c.name) LIKE LOWER(:company_name)
                AND i.profile->'data'->'company'->'contact' IS NOT NULL
            """
            
            params = {"company_name": f"%{company_name}%"}
            
            # Add investor filtering if provided
            if investor_id:
                base_query += " AND d.\"investorId\"::text = :investor_id"
                params["investor_id"] = investor_id
            
            base_query += " LIMIT 1"
            query = text(base_query)
            
            result = conn.execute(query, params)
            row = result.fetchone()
            
            if row:
                return {
                    "email": row[0] if row[0] else None,
                    "phone": row[1] if row[1] else None,
                    "website": row[2] if row[2] else None,
                    "company_name": row[3]
                }
            return {}
    except Exception as e:
        logger.error(f"Error querying contact info for {company_name}: {e}")
        return {}

def query_founder_info_for_company(company_name: str, investor_id: str = None) -> List[Dict[str, Any]]:
    """Query founder information for a specific company using JSONB"""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            # Query insights table for team data (which contains founders) with optional investor filtering
            base_query = """
                SELECT 
                    jsonb_array_elements(i.profile->'data'->'team') as team_member,
                    c.name as company_name
                FROM insights i
                JOIN deals d ON i."dealId"::text = d.id::text
                JOIN companies c ON d."startupId"::text = c.id::text
                WHERE LOWER(c.name) LIKE LOWER(:company_name)
                AND i.profile->'data'->'team' IS NOT NULL
            """
            
            params = {"company_name": f"%{company_name}%"}
            
            # Add investor filtering if provided
            if investor_id:
                base_query += " AND d.\"investorId\"::text = :investor_id"
                params["investor_id"] = investor_id
            
            query = text(base_query)
            
            result = conn.execute(query, params)
            founders = []
            seen_founders = set()
            
            for row in result:
                if row[0]:
                    team_member = row[0]
                    position = team_member.get("position", "").lower()
                    
                    # Filter for founders and key leadership (look for "founder", "ceo", "cto" in position)
                    if any(title in position for title in ["founder", "ceo", "cto"]):
                        name = team_member.get("name")
                        # Deduplicate by name
                        if name and name not in seen_founders:
                            seen_founders.add(name)
                            founders.append({
                                "name": name,
                                "position": team_member.get("position"),
                                "experience": team_member.get("experience"),
                                "company_name": row[1]
                            })
            
            return founders
    except Exception as e:
        logger.error(f"Error querying founder info for {company_name}: {e}")
        return []

def query_financial_metrics_for_company(company_name: str, investor_id: str = None) -> Dict[str, Any]:
    """Query financial metrics for a specific company using JSONB"""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            # Query insights table for financial data with optional investor filtering
            base_query = """
                SELECT 
                    i.profile->'data'->'financials'->'revenue'->>'recent' as recent_revenue,
                    i.profile->'data'->'financials'->'revenue'->>'projection' as revenue_projection,
                    i.profile->'data'->'financials'->'funding'->>'total_funding' as total_funding,
                    i.profile->'data'->'financials'->>'valuation' as valuation,
                    i.profile->'data'->'traction'->>'monthly_recurring_revenue' as mrr,
                    i.profile->'data'->'traction'->>'customer_count' as customer_count,
                    c.name as company_name
                FROM insights i
                JOIN deals d ON i."dealId"::text = d.id::text
                JOIN companies c ON d."startupId"::text = c.id::text
                WHERE LOWER(c.name) LIKE LOWER(:company_name)
                AND i.profile->'data'->'financials' IS NOT NULL
            """
            
            params = {"company_name": f"%{company_name}%"}
            
            # Add investor filtering if provided
            if investor_id:
                base_query += " AND d.\"investorId\"::text = :investor_id"
                params["investor_id"] = investor_id
            
            base_query += " LIMIT 1"
            query = text(base_query)
            
            result = conn.execute(query, params)
            row = result.fetchone()
            
            if row:
                def safe_float(value):
                    try:
                        return float(value) if value else None
                    except (ValueError, TypeError):
                        return None
                
                def safe_int(value):
                    try:
                        return int(value) if value else None
                    except (ValueError, TypeError):
                        return None
                
                return {
                    "recent_revenue": safe_float(row[0]),
                    "revenue_projection": safe_float(row[1]),
                    "total_funding": safe_float(row[2]),
                    "valuation": safe_float(row[3]),
                    "monthly_recurring_revenue": safe_float(row[4]),
                    "customer_count": safe_int(row[5]),
                    "company_name": row[6]
                }
            return {}
    except Exception as e:
        logger.error(f"Error querying financial metrics for {company_name}: {e}")
        return {}

def extract_company_name_from_query(query: str) -> Optional[str]:
    """Extract company name from query text"""
    query_lower = query.lower()
    
    # Common patterns for company name extraction
    patterns = [
        r'(?:for|of|about)\s+([a-zA-Z0-9\s]+?)(?:\s+(?:company|corp|inc|ltd))?(?:\?|$|\s+(?:tam|email|contact|founder|revenue))',
        r'([a-zA-Z0-9\s]+?)(?:\s+(?:company|corp|inc|ltd))?\s+(?:tam|email|contact|founder|revenue)',
        r'(?:company|startup)\s+([a-zA-Z0-9\s]+?)(?:\?|$)',
    ]
    
    import re
    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            company_name = match.group(1).strip()
            # Clean up common words
            company_name = re.sub(r'\b(?:the|a|an|company|corp|inc|ltd)\b', '', company_name).strip()
            if len(company_name) > 1:
                return company_name
    
    # Fallback: look for known company names
    known_companies = ['11sight', 'elevensight']
    for company in known_companies:
        if company in query_lower:
            return company
    
    return None

def company_exists_in_database(company_name: str, investor_id: str = None) -> Tuple[bool, Optional[str]]:
    """Check if a company exists in the database and return its actual name"""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            # Query to find company with optional investor filtering
            base_query = """
                SELECT DISTINCT c.name as company_name
                FROM companies c
                JOIN deals d ON c.id::text = d."startupId"::text
                WHERE LOWER(c.name) LIKE LOWER(:company_name)
            """
            
            params = {"company_name": f"%{company_name}%"}
            
            # Add investor filtering if provided
            if investor_id:
                base_query += " AND d.\"investorId\"::text = :investor_id"
                params["investor_id"] = investor_id
            
            base_query += " LIMIT 1"
            query = text(base_query)
            
            result = conn.execute(query, params)
            row = result.fetchone()
            
            if row:
                return True, row[0]
            return False, None
            
    except Exception as e:
        logger.error(f"Error checking if company {company_name} exists: {e}")
        return False, None

def get_comprehensive_company_financials(company_name: str, investor_id: str = None) -> Dict[str, Any]:
    """Get all comprehensive financial metrics for a company"""
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            # First check if company exists
            exists, actual_name = company_exists_in_database(company_name, investor_id)
            if not exists:
                return {"error": f"Company '{company_name}' not found in database", "company_exists": False}
            
            # Comprehensive query for all financial metrics
            base_query = """
                SELECT 
                    c.name as company_name,
                    d.status as deal_status,
                    
                    -- Latest funding round info
                    i.profile->'data'->'financials'->'funding'->'rounds' as funding_rounds,
                    i.profile->'data'->'financials'->'funding'->>'total_funding' as total_funding,
                    
                    -- Future funding plans
                    i.profile->'data'->'financials'->'funding'->'future_plans' as future_plans,
                    
                    -- Revenue metrics
                    i.profile->'data'->'financials'->'revenue'->>'recent' as recent_revenue,
                    i.profile->'data'->'financials'->'revenue'->>'projection' as revenue_projection,
                    
                    -- Orbe valuation
                    i.market->'data'->>'valuation' as orbe_valuation,
                    
                    -- Customer metrics
                    i.profile->'data'->'financials'->'metrics'->>'cac' as cac,
                    i.profile->'data'->'financials'->'metrics'->>'ltv' as ltv,
                    
                    -- ARR and other metrics
                    i.profile->'data'->'traction'->>'monthly_recurring_revenue' as mrr,
                    i.profile->'data'->'traction'->>'annual_recurring_revenue' as arr
                    
                FROM insights i
                JOIN deals d ON i."dealId"::text = d.id::text
                JOIN companies c ON d."startupId"::text = c.id::text
                WHERE LOWER(c.name) LIKE LOWER(:company_name)
            """
            
            params = {"company_name": f"%{company_name}%"}
            
            # Add investor filtering if provided
            if investor_id:
                base_query += " AND d.\"investorId\"::text = :investor_id"
                params["investor_id"] = investor_id
            
            base_query += " LIMIT 1"
            query = text(base_query)
            
            result = conn.execute(query, params)
            row = result.fetchone()
            
            if not row:
                return {"error": f"No financial data found for company '{company_name}'", "company_exists": True}
            
            # Helper functions
            def safe_float(value):
                try:
                    return float(value) if value and str(value).strip() and str(value) != 'null' else None
                except (ValueError, TypeError):
                    return None
            
            def safe_int(value):
                try:
                    return int(value) if value and str(value).strip() and str(value) != 'null' else None
                except (ValueError, TypeError):
                    return None
            
            # Parse funding rounds
            funding_rounds = row[2] if row[2] else []
            latest_funding_round = None
            latest_funding_amount = None
            total_investors = 0
            
            if funding_rounds and isinstance(funding_rounds, list) and len(funding_rounds) > 0:
                # Get the latest funding round (last in array)
                latest_round = funding_rounds[-1]
                latest_funding_round = latest_round.get('stage', 'Unknown')
                latest_funding_amount = safe_float(latest_round.get('amount'))
                
                # Count total unique investors across all rounds
                all_investors = set()
                for round_data in funding_rounds:
                    contributors = round_data.get('contributors', [])
                    for contributor in contributors:
                        all_investors.add(contributor.get('name', ''))
                total_investors = len(all_investors)
            
            # Parse future funding plans
            future_plans = row[4] if row[4] else []
            new_funding_ask = None
            if future_plans and isinstance(future_plans, list) and len(future_plans) > 0:
                # Get the first planned funding round
                planned_round = future_plans[0]
                new_funding_ask = safe_float(planned_round.get('target_amount'))
            
            return {
                "company_exists": True,
                "company_name": row[0],
                "deal_status": row[1],
                
                # Funding metrics
                "latest_funding_round": latest_funding_round,
                "latest_funding_amount": latest_funding_amount,
                "total_funding": safe_float(row[3]),
                "num_investors": total_investors,
                "new_funding_ask": new_funding_ask,
                
                # Revenue metrics
                "revenue": safe_float(row[5]),
                "revenue_projection": safe_float(row[6]),
                
                # Valuation
                "orbe_valuation": safe_float(row[7]),
                
                # Customer metrics
                "cac": safe_float(row[8]),
                "ltv": safe_float(row[9]),
                
                # Recurring revenue
                "mrr": safe_float(row[10]),
                "arr": safe_float(row[11])
            }
            
    except Exception as e:
        logger.error(f"Error getting comprehensive financials for {company_name}: {e}")
        return {"error": f"Database error: {str(e)}", "company_exists": False}

def detect_specific_data_query(query: str) -> Optional[str]:
    """Detect if the query is asking for specific data that can be answered with direct SQL"""
    query_lower = query.lower()
    
    # Comprehensive financial metrics detection
    financial_keywords = [
        'funding', 'funding round', 'latest funding', 'total funding', 'funding amount',
        'investors', 'number of investors', 'how many investors',
        'revenue', 'arr', 'annual recurring revenue', 'mrr', 'monthly recurring revenue',
        'valuation', 'orbe valuation', 'current valuation',
        'status', 'current status', 'deal status',
        'cac', 'customer acquisition cost',
        'ltv', 'lifetime value', 'customer lifetime value',
        'funding ask', 'new funding', 'series a', 'series b', 'planned funding'
    ]
    
    # TAM queries
    if any(term in query_lower for term in ['tam', 'total addressable market', 'market size']):
        return "tam"
    
    # Contact queries
    if any(term in query_lower for term in ['email', 'contact', 'phone', 'website']):
        return "contact"
    
    # Founder queries
    if any(term in query_lower for term in ['founder', 'ceo', 'founder email']):
        return "founder"
    
    # Comprehensive financial queries
    if any(term in query_lower for term in financial_keywords):
        return "comprehensive_financial"
    
    return None

def execute_specific_data_query(query: str, query_type: str, investor_id: str = None) -> Optional[Dict[str, Any]]:
    """Execute a specific data query using direct SQL"""
    try:
        # Extract company name from query
        company_name = extract_company_name_from_query(query)
        if not company_name:
            return {
                "type": "error",
                "formatted_response": "I couldn't identify a specific company name in your query. Please specify which company you'd like information about."
            }
        
        if query_type == "comprehensive_financial":
            financial_data = get_comprehensive_company_financials(company_name, investor_id)
            
            if not financial_data.get("company_exists"):
                return {
                    "type": "error", 
                    "company": company_name,
                    "formatted_response": f"Company '{company_name}' was not found in the database. Please check the company name and try again."
                }
            
            if financial_data.get("error"):
                return {
                    "type": "error",
                    "company": company_name, 
                    "formatted_response": financial_data["error"]
                }
            
            # Format comprehensive response
            response_parts = [f"Financial Summary for {financial_data['company_name']}:"]
            
            # Current Status
            if financial_data.get('deal_status'):
                response_parts.append(f"Current Status: {financial_data['deal_status'].title()}")
            
            # Latest Funding Round
            if financial_data.get('latest_funding_round'):
                funding_text = f"Latest Funding Round: {financial_data['latest_funding_round']}"
                if financial_data.get('latest_funding_amount'):
                    funding_text += f" - ${financial_data['latest_funding_amount']:,.0f}"
                response_parts.append(funding_text)
            else:
                response_parts.append("Latest Funding Round: Not available for this deal")
            
            # Total Funding
            if financial_data.get('total_funding'):
                response_parts.append(f"Total Funding To Date: ${financial_data['total_funding']:,.0f}")
            else:
                response_parts.append("Total Funding To Date: Not available for this deal")
            
            # Number of Investors
            if financial_data.get('num_investors'):
                response_parts.append(f"Number of Investors: {financial_data['num_investors']}")
            else:
                response_parts.append("Number of Investors: Not available for this deal")
            
            # New Funding Ask
            if financial_data.get('new_funding_ask'):
                response_parts.append(f"New Funding Round Ask: ${financial_data['new_funding_ask']:,.0f}")
            else:
                response_parts.append("New Funding Round Ask: Not available for this deal")
            
            # Revenue
            if financial_data.get('revenue'):
                response_parts.append(f"Revenue: ${financial_data['revenue']:,.0f}")
            else:
                response_parts.append("Revenue: Not available for this deal")
            
            # ARR
            if financial_data.get('arr'):
                response_parts.append(f"ARR: ${financial_data['arr']:,.0f}")
            elif financial_data.get('mrr'):
                # Calculate ARR from MRR if available
                arr_calculated = financial_data['mrr'] * 12
                response_parts.append(f"ARR: ${arr_calculated:,.0f} (calculated from MRR)")
            else:
                response_parts.append("ARR: Not available for this deal")
            
            # Orbe Valuation
            if financial_data.get('orbe_valuation'):
                response_parts.append(f"Orbe Valuation: ${financial_data['orbe_valuation']:,.0f}")
            else:
                response_parts.append("Orbe Valuation: Not available for this deal")
            
            # CAC
            if financial_data.get('cac'):
                response_parts.append(f"CAC: ${financial_data['cac']:,.0f}")
            else:
                response_parts.append("CAC: Not available for this deal")
            
            # LTV
            if financial_data.get('ltv'):
                response_parts.append(f"LTV: ${financial_data['ltv']:,.0f}")
            else:
                response_parts.append("LTV: Not available for this deal")
            
            return {
                "type": "comprehensive_financial",
                "company": company_name,
                "data": financial_data,
                "formatted_response": "\n".join(response_parts)
            }
        
        elif query_type == "tam":
            tam_data = query_tam_for_company(company_name, investor_id)
            if tam_data and (tam_data.get('orbe_estimate') or tam_data.get('company_report')):
                response_parts = [f"Total Addressable Market (TAM) for {tam_data.get('company_name', company_name)}:"]
                
                # Add Orbe estimate if available
                if tam_data.get('orbe_estimate'):
                    orbe_part = f"Orbe Estimate: ${tam_data['orbe_estimate']:,.0f}"
                    if tam_data.get('orbe_source'):
                        orbe_part += f" (Source: Market Research)"
                    response_parts.append(orbe_part)
                
                # Add company report if available
                if tam_data.get('company_report'):
                    company_part = f"Company Report: ${tam_data['company_report']:,.0f}"
                    response_parts.append(company_part)
                
                # Add explanation if both values exist and differ significantly
                if (tam_data.get('orbe_estimate') and tam_data.get('company_report') and 
                    abs(tam_data['orbe_estimate'] - tam_data['company_report']) / max(tam_data['orbe_estimate'], tam_data['company_report']) > 0.1):
                    response_parts.append("Note: Orbe estimates are based on third-party market research, while company reports reflect the company's own market assessment.")
                
                return {
                    "type": "tam",
                    "company": company_name,
                    "data": tam_data,
                    "formatted_response": "\n".join(response_parts)
                }
            else:
                # Check if company exists
                exists, actual_name = company_exists_in_database(company_name, investor_id)
                if not exists:
                    return {
                        "type": "error",
                        "company": company_name,
                        "formatted_response": f"Company '{company_name}' was not found in the database. Please check the company name and try again."
                    }
                else:
                    return {
                        "type": "tam",
                        "company": company_name,
                        "formatted_response": f"TAM data is not available for {actual_name} in this deal."
                    }
        
        elif query_type == "contact":
            contact_info = query_contact_info_for_company(company_name, investor_id)
            # Check if there's actually useful contact data (not just None values)
            if contact_info and any(contact_info.get(field) for field in ['email', 'phone', 'website']):
                response_parts = [f"Contact information for {contact_info.get('company_name', company_name)}:"]
                if contact_info.get('email'):
                    response_parts.append(f"Email: {contact_info['email']}")
                if contact_info.get('phone'):
                    response_parts.append(f"Phone: {contact_info['phone']}")
                if contact_info.get('website'):
                    response_parts.append(f"Website: {contact_info['website']}")
                
                return {
                    "type": "contact",
                    "company": company_name,
                    "data": contact_info,
                    "formatted_response": " | ".join(response_parts)
                }
            else:
                # Check if company exists
                exists, actual_name = company_exists_in_database(company_name, investor_id)
                if not exists:
                    return {
                        "type": "error",
                        "company": company_name,
                        "formatted_response": f"Company '{company_name}' was not found in the database. Please check the company name and try again."
                    }
                else:
                    return {
                        "type": "contact",
                        "company": company_name,
                        "formatted_response": f"Contact information is not available for {actual_name} in this deal."
                    }
        
        elif query_type == "founder":
            founders = query_founder_info_for_company(company_name, investor_id)
            if founders:
                response_parts = [f"Founders of {founders[0].get('company_name', company_name)}:\n"]
                for founder in founders:
                    founder_info = f"• {founder.get('name', 'Unknown')}"
                    if founder.get('position'):
                        founder_info += f" - {founder['position']}"
                    if founder.get('experience'):
                        # Truncate experience to keep response manageable
                        exp = founder['experience'][:150] + "..." if len(founder['experience']) > 150 else founder['experience']
                        founder_info += f"\n  Experience: {exp}"
                    response_parts.append(founder_info)
                
                return {
                    "type": "founder",
                    "company": company_name,
                    "data": founders,
                    "formatted_response": "\n".join(response_parts)
                }
            else:
                # Check if company exists
                exists, actual_name = company_exists_in_database(company_name, investor_id)
                if not exists:
                    return {
                        "type": "error",
                        "company": company_name,
                        "formatted_response": f"Company '{company_name}' was not found in the database. Please check the company name and try again."
                    }
                else:
                    return {
                        "type": "founder",
                        "company": company_name,
                        "formatted_response": f"Founder information is not available for {actual_name} in this deal."
                    }
        
        return None
    except Exception as e:
        logger.error(f"Error executing specific data query: {e}")
        return {
            "type": "error",
            "formatted_response": f"An error occurred while retrieving the information: {str(e)}"
        }