"""
Entity Extractor for Audit Management System
Integrates entity recognition with data filtering and retrieval
"""

import re
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from difflib import SequenceMatcher

# Import from database.py in same directory
from database import get_cached_data, refresh_all_data

class AuditEntityRecognizer:
    """
    Enhanced entity recognition system for retrieval scenarios
    Extracts audit, device, time, and retrieval entities from user text
    """
    
    def __init__(self):
        # Confidence thresholds
        self.fuzzy_threshold = 0.70
        self.category_fuzzy_threshold = 0.70
        
        # Confidence scores
        self.confidence_scores = {
            "exact": 1.0,
            "fuzzy": 0.85,
            "category": 0.80,
            "alias": 0.80,
            "time": 0.90,
            "device": 0.85
        }
        
        # Initialize data references
        self.data = None
        self.audit_names = []
        self.audit_ids = []
        self.audit_categories = []
        self.device_names = []
        self.device_categories = []
        self.audit_aliases = {}
        self.audit_device_compatibility = {}
        
        # Load data from database
        self.load_data_references()
        
        # Time patterns
        self.time_patterns = {
            'relative': {
                r'\blast\s+week\b': {'days': -7, 'type': 'week'},
                r'\bthis\s+week\b': {'days': 0, 'type': 'week'},
                r'\blast\s+month\b': {'days': -30, 'type': 'month'},
                r'\bthis\s+month\b': {'days': 0, 'type': 'month'},
                r'\byesterday\b': {'days': -1, 'type': 'day'},
                r'\btoday\b': {'days': 0, 'type': 'day'},
                r'\blast\s+(\d+)\s+days?\b': {'pattern': 'last_n_days'},
                r'\bsince\s+last\s+monday\b': {'days': -7, 'type': 'since_monday'},
                r'\bpast\s+week\b': {'days': -7, 'type': 'week'},
                r'\brecent\b': {'days': -7, 'type': 'recent'}
            },
            'absolute': {
                r'\b(january|jan)\s+(\d{4})\b': {'month': 1},
                r'\b(february|feb)\s+(\d{4})\b': {'month': 2},
                r'\b(march|mar)\s+(\d{4})\b': {'month': 3},
                r'\b(april|apr)\s+(\d{4})\b': {'month': 4},
                r'\b(may)\s+(\d{4})\b': {'month': 5},
                r'\b(june|jun)\s+(\d{4})\b': {'month': 6},
                r'\b(july|jul)\s+(\d{4})\b': {'month': 7},
                r'\b(august|aug)\s+(\d{4})\b': {'month': 8},
                r'\b(september|sep)\s+(\d{4})\b': {'month': 9},
                r'\b(october|oct)\s+(\d{4})\b': {'month': 10},
                r'\b(november|nov)\s+(\d{4})\b': {'month': 11},
                r'\b(december|dec)\s+(\d{4})\b': {'month': 12}
            }
        }
    
    def load_data_references(self):
        """Load data references from database cache"""
        try:
            self.data = get_cached_data()
            if self.data:
                # Load the lists from cached data
                self.audit_names = self.data.get("audit_names", [])
                self.audit_ids = self.data.get("audit_ids", [])
                self.audit_categories = self.data.get("audit_categories", [])
                self.device_names = self.data.get("device_names", [])
                self.device_categories = self.data.get("device_categories", [])
                self.audit_aliases = self.data.get("audit_aliases", {})
                self.audit_device_compatibility = self.data.get("audit_device_compatibility", {})
                
                # Create name to ID and ID to name mappings
                self.audit_name_to_id = {}
                self.audit_id_to_name = {}
                
                # Build mappings from the full audit data
                for audit in self.data.get("audits", []):
                    audit_id = audit["audit_id"]
                    audit_name = audit["audit_name"]
                    self.audit_name_to_id[audit_name] = audit_id
                    self.audit_id_to_name[audit_id] = audit_name
                
                # Create reverse alias mapping
                self.alias_to_audit = {}
                for audit_name, aliases in self.audit_aliases.items():
                    for alias in aliases:
                        self.alias_to_audit[alias.lower()] = audit_name
            else:
                print("AuditEntityRecognizer: No cached data available")
        except Exception as e:
            print(f"AuditEntityRecognizer: Error loading data: {e}")
    
    def refresh_data(self):
        """Refresh data from database"""
        self.load_data_references()
    
    def similarity(self, a: str, b: str) -> float:
        """Calculate similarity between two strings"""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    
    def preprocess_text(self, text: str) -> str:
        """Clean and preprocess text for matching"""
        text = re.sub(r'[^\w\s]', ' ', text)
        text = ' '.join(text.split())
        return text.lower()
    
    def extract_audit_entities(self, text: str) -> Dict[str, Any]:
        """Extract audit-related entities"""
        text_clean = self.preprocess_text(text)
        entities = {}
        
        # Extract audit ID
        audit_id_patterns = [
            r'\baudit\s+(?:id\s+)?(\d+)\b',
            r'\bid\s+(\d+)\b'
        ]
        
        for pattern in audit_id_patterns:
            matches = re.findall(pattern, text_clean)
            for match in matches:
                if match in self.audit_ids:
                    audit_name = self.audit_id_to_name.get(match, "")
                    entities.update({
                        "audit_id": {"value": match, "confidence": self.confidence_scores["exact"]},
                        "audit_name": {"value": audit_name, "confidence": self.confidence_scores["exact"]}
                    })
                    return entities
        
        # Extract exact audit name
        for audit_name in self.audit_names:
            if audit_name.lower() in text_clean:
                audit_id = self.audit_name_to_id.get(audit_name, "")
                entities.update({
                    "audit_name": {"value": audit_name, "confidence": self.confidence_scores["exact"]},
                    "audit_id": {"value": audit_id, "confidence": self.confidence_scores["exact"]}
                })
                return entities
        
        # Extract aliases
        for alias, audit_name in self.alias_to_audit.items():
            if alias in text_clean:
                audit_id = self.audit_name_to_id.get(audit_name, "")
                entities.update({
                    "audit_name": {"value": audit_name, "confidence": self.confidence_scores["alias"]},
                    "audit_id": {"value": audit_id, "confidence": self.confidence_scores["alias"]}
                })
                return entities
        
        # Extract category
        for category in self.audit_categories:
            # Exact match
            if category in text_clean:
                entities["audit_category"] = {"value": category, "confidence": self.confidence_scores["category"]}
                return entities
            
            # Fuzzy match for typos
            text_words = text_clean.split()
            for word in text_words:
                similarity_score = self.similarity(word, category)
                if similarity_score >= self.category_fuzzy_threshold:
                    length_diff = abs(len(word) - len(category))
                    if length_diff <= 2:
                        entities["audit_category"] = {"value": category, "confidence": self.confidence_scores["fuzzy"]}
                        return entities
        
        return entities
    
    def extract_device_entities(self, text: str) -> Dict[str, Any]:
        """Extract device-related entities"""
        text_clean = self.preprocess_text(text)
        entities = {}
        
        # Extract device names
        for device_name in self.device_names:
            if device_name in text_clean:
                entities["device_name"] = {"value": device_name, "confidence": self.confidence_scores["exact"]}
                break
        
        # Extract device categories
        for device_category in self.device_categories:
            if device_category in text_clean:
                entities["device_category"] = {"value": device_category, "confidence": self.confidence_scores["device"]}
                break
        
        return entities
    
    def extract_time_entities(self, text: str) -> Dict[str, Any]:
        """Extract time-related entities"""
        text_clean = self.preprocess_text(text)
        entities = {}
        
        # Check relative time patterns
        for pattern, time_info in self.time_patterns['relative'].items():
            if re.search(pattern, text_clean):
                if 'pattern' in time_info and time_info['pattern'] == 'last_n_days':
                    # Extract number of days
                    match = re.search(r'\blast\s+(\d+)\s+days?\b', text_clean)
                    if match:
                        days = int(match.group(1))
                        entities["time_range"] = {
                            "value": f"last_{days}_days",
                            "type": "relative",
                            "days_offset": -days,
                            "confidence": self.confidence_scores["time"]
                        }
                else:
                    entities["time_range"] = {
                        "value": pattern.replace(r'\b', '').replace(r'\s+', '_'),
                        "type": "relative",
                        "days_offset": time_info.get('days', 0),
                        "time_type": time_info.get('type', 'unknown'),
                        "confidence": self.confidence_scores["time"]
                    }
                break
        
        # Check absolute time patterns (months/years)
        for pattern, time_info in self.time_patterns['absolute'].items():
            match = re.search(pattern, text_clean)
            if match:
                month_name = match.group(1)
                year = int(match.group(2))
                entities["time_range"] = {
                    "value": f"{month_name}_{year}",
                    "type": "absolute",
                    "month": time_info["month"],
                    "year": year,
                    "confidence": self.confidence_scores["time"]
                }
                break
        
        return entities
    
    def extract_retrieval_type(self, text: str) -> Dict[str, Any]:
        """Extract what type of data user wants to retrieve"""
        text_clean = self.preprocess_text(text)
        entities = {}
        
        # Patterns for different retrieval types
        if re.search(r'\b(reports?|results?|execution|history)\b', text_clean):
            entities["retrieval_type"] = {"value": "reports", "confidence": self.confidence_scores["exact"]}
        elif re.search(r'\b(devices?|machines?|systems?)\b', text_clean):
            entities["retrieval_type"] = {"value": "devices", "confidence": self.confidence_scores["exact"]}
        elif re.search(r'\b(audits?|checks?|scans?)\b', text_clean):
            entities["retrieval_type"] = {"value": "audits", "confidence": self.confidence_scores["exact"]}
        else:
            # Default to audits if not specified
            entities["retrieval_type"] = {"value": "audits", "confidence": 0.5}
        
        return entities
    
    def recognize_entities(self, text: str) -> Dict[str, Any]:
        """
        Main method to extract all entities from text for retrieval scenarios
        
        Args:
            text: User input text
            
        Returns:
            Dict containing all extracted entities
        """
        entities = {}
        
        # Extract all entity types
        audit_entities = self.extract_audit_entities(text)
        device_entities = self.extract_device_entities(text)
        time_entities = self.extract_time_entities(text)
        retrieval_entities = self.extract_retrieval_type(text)
        
        # Combine all entities
        entities.update(audit_entities)
        entities.update(device_entities)
        entities.update(time_entities)
        entities.update(retrieval_entities)
        
        # Calculate overall confidence
        confidences = [entity["confidence"] for entity in entities.values() if isinstance(entity, dict) and "confidence" in entity]
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        return {
            "entities": entities,
            "overall_confidence": overall_confidence
        }


class EntityExtractor:
    """
    Entity extractor that integrates entity recognition with data filtering
    """
    
    def __init__(self):
        self.entity_recognizer = AuditEntityRecognizer()
        self.data = None
        self.load_data()
    
    def load_data(self):
        """Load data from database"""
        try:
            self.data = get_cached_data()
            if self.data:
                pass
            else:
                print("EntityExtractor: Failed to load data")
        except Exception as e:
            print(f"EntityExtractor: Error loading data: {e}")
            self.data = None
    
    def refresh_data(self):
        """Force refresh of data from database"""
        try:
            self.data = refresh_all_data()
            # Also refresh the entity recognizer data
            self.entity_recognizer.refresh_data()
        except Exception as e:
            print(f"EntityExtractor: Error refreshing data: {e}")
    
    def parse_time_range(self, time_entity: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Parse time entity into start and end datetime objects"""
        if not time_entity:
            return None, None
        
        now = datetime.now()
        
        if time_entity.get("type") == "relative":
            days_offset = time_entity.get("days_offset", 0)
            
            if time_entity.get("time_type") == "week":
                # For week, get start of week
                start_date = now + timedelta(days=days_offset)
                start_date = start_date - timedelta(days=start_date.weekday())  # Monday
                end_date = start_date + timedelta(days=6)  # Sunday
            elif time_entity.get("time_type") == "month":
                if days_offset == 0:  # This month
                    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    next_month = start_date.replace(month=start_date.month + 1) if start_date.month < 12 else start_date.replace(year=start_date.year + 1, month=1)
                    end_date = next_month - timedelta(days=1)
                else:  # Last month
                    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    start_date = start_date.replace(month=start_date.month - 1) if start_date.month > 1 else start_date.replace(year=start_date.year - 1, month=12)
                    end_date = now.replace(day=1) - timedelta(days=1)
            else:
                # For days
                start_date = now + timedelta(days=days_offset)
                end_date = now if days_offset < 0 else start_date + timedelta(days=1)
            
            return start_date, end_date
        
        elif time_entity.get("type") == "absolute":
            year = time_entity.get("year")
            month = time_entity.get("month")
            
            if year and month:
                start_date = datetime(year, month, 1)
                if month == 12:
                    end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
                else:
                    end_date = datetime(year, month + 1, 1) - timedelta(days=1)
                return start_date, end_date
        
        return None, None
    
    def filter_audits(self, entities: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Filter audits based on entities"""
        if not self.data or not self.data.get("audits"):
            return []
        
        audits = self.data["audits"]
        filtered_audits = []
        
        # Filter by specific audit
        if "audit_id" in entities:
            audit_id = entities["audit_id"]["value"]  # Keep as string for consistency
            filtered_audits = [audit for audit in audits if audit["audit_id"] == audit_id]
        elif "audit_name" in entities:
            audit_name = entities["audit_name"]["value"]
            filtered_audits = [audit for audit in audits if audit["audit_name"] == audit_name]
        elif "audit_category" in entities:
            category = entities["audit_category"]["value"]
            filtered_audits = [audit for audit in audits if audit["audit_category"] == category]
        else:
            filtered_audits = audits
        
        # Further filter by device compatibility if device is specified
        if "device_category" in entities:
            device_category = entities["device_category"]["value"]
            filtered_audits = [audit for audit in filtered_audits 
                             if device_category in audit.get("device_categories", [])]
        
        return filtered_audits
    
    def filter_devices(self, entities: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Filter devices based on entities"""
        if not self.data or not self.data.get("devices"):
            return []
        
        devices = self.data["devices"]
        filtered_devices = []
        
        if "device_name" in entities:
            device_name = entities["device_name"]["value"]
            filtered_devices = [device for device in devices if device["device_name"] == device_name]
        elif "device_category" in entities:
            device_category = entities["device_category"]["value"]
            filtered_devices = [device for device in devices if device["device_category"] == device_category]
        else:
            filtered_devices = devices
        
        return filtered_devices
    
    def filter_reports(self, entities: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Filter reports based on entities"""
        if not self.data or not self.data.get("reports"):
            return []
        
        reports = self.data["reports"]
        filtered_reports = []
        
        # Start with all reports
        filtered_reports = reports
        
        # Filter by audit
        if "audit_id" in entities:
            audit_id = entities["audit_id"]["value"]  # Keep as string for consistency
            filtered_reports = [report for report in filtered_reports if report["audit_id"] == audit_id]
        elif "audit_name" in entities:
            audit_name = entities["audit_name"]["value"]
            filtered_reports = [report for report in filtered_reports if report["audit_name"] == audit_name]
        elif "audit_category" in entities:
            # Need to get audit IDs for this category first
            category_audits = self.filter_audits(entities)
            category_audit_ids = [audit["audit_id"] for audit in category_audits]
            filtered_reports = [report for report in filtered_reports if report["audit_id"] in category_audit_ids]
        
        # Filter by device
        if "device_name" in entities:
            device_name = entities["device_name"]["value"]
            filtered_reports = [report for report in filtered_reports if report["device_name"] == device_name]
        elif "device_category" in entities:
            # Need to get device IDs for this category first
            category_devices = self.filter_devices(entities)
            category_device_ids = [device["device_id"] for device in category_devices]
            filtered_reports = [report for report in filtered_reports if report["device_id"] in category_device_ids]
        
        # Filter by time
        if "time_range" in entities:
            start_date, end_date = self.parse_time_range(entities["time_range"])
            if start_date and end_date:
                time_filtered_reports = []
                for report in filtered_reports:
                    if report["execution_time"]:
                        try:
                            exec_time = datetime.fromisoformat(report["execution_time"].replace('Z', '+00:00'))
                            if start_date <= exec_time <= end_date:
                                time_filtered_reports.append(report)
                        except:
                            continue
                filtered_reports = time_filtered_reports
        
        return filtered_reports
    
    def format_response(self, filtered_data: Dict[str, List], entities: Dict[str, Any]) -> Dict[str, Any]:
        """Format the filtered data into a user-friendly response"""
        retrieval_type = entities.get("retrieval_type", {}).get("value", "audits")
        
        response = {
            "success": True,
            "retrieval_type": retrieval_type,
            "entities_found": entities,
            "data": filtered_data,
            "summary": {
                "total_audits": len(filtered_data.get("audits", [])),
                "total_devices": len(filtered_data.get("devices", [])),
                "total_reports": len(filtered_data.get("reports", []))
            }
        }
        
        # Add a human-readable message
        if retrieval_type == "reports":
            if response["summary"]["total_reports"] > 0:
                response["message"] = f"Found {response['summary']['total_reports']} reports matching your criteria."
            else:
                response["message"] = "No reports found matching your criteria."
        elif retrieval_type == "devices":
            if response["summary"]["total_devices"] > 0:
                response["message"] = f"Found {response['summary']['total_devices']} devices matching your criteria."
            else:
                response["message"] = "No devices found matching your criteria."
        else:  # audits
            if response["summary"]["total_audits"] > 0:
                response["message"] = f"Found {response['summary']['total_audits']} audits matching your criteria."
            else:
                response["message"] = "No audits found matching your criteria."
        
        return response
    
    def get_filtered_data(self, user_text: str) -> Dict[str, Any]:
        """
        Main method: Extract entities and return filtered data
        This is called by the retrieval agent
        
        Args:
            user_text: User input text
            
        Returns:
            Dict containing filtered data and metadata
        """
        try:
            # Check if data is loaded
            if not self.data:
                return {
                    "success": False,
                    "error": "Data not loaded. Please try again.",
                    "data": {"audits": [], "devices": [], "reports": []},
                    "summary": {"total_audits": 0, "total_devices": 0, "total_reports": 0}
                }
            
            print(f"EntityExtractor: Processing query: '{user_text}'")
            
            # Extract entities
            entity_result = self.entity_recognizer.recognize_entities(user_text)
            entities = entity_result.get("entities", {})
            
            print(f"EntityExtractor: Extracted entities: {entities}")
            
            # Filter data based on entities
            filtered_audits = self.filter_audits(entities)
            filtered_devices = self.filter_devices(entities)
            filtered_reports = self.filter_reports(entities)
            
            filtered_data = {
                "audits": filtered_audits,
                "devices": filtered_devices,
                "reports": filtered_reports
            }
            
            # Format response
            response = self.format_response(filtered_data, entities)
            return response
            
        except Exception as e:
            print(f"EntityExtractor: Error processing query: {e}")
            return {
                "success": False,
                "error": f"Error processing query: {str(e)}",
                "data": {"audits": [], "devices": [], "reports": []},
                "summary": {"total_audits": 0, "total_devices": 0, "total_reports": 0}
            }


# Factory function for easy integration
def create_entity_extractor() -> EntityExtractor:
    """Factory function to create an EntityExtractor instance"""
    return EntityExtractor()


# Convenience function for direct usage
def get_filtered_data(user_text: str) -> Dict[str, Any]:
    """
    Convenience function for getting filtered data
    
    Args:
        user_text: User input text
        
    Returns:
        Dict containing filtered data
    """
    extractor = create_entity_extractor()
    return extractor.get_filtered_data(user_text)


# Example usage and testing
if __name__ == "__main__":
    # Test examples
    test_cases = [
        "show me all audits",
        "list security audits",
        "execute security audits",
        "retrieve security related audits",
        "show audit history from last week",
        "get device information for routers"
    ]
    
    extractor = create_entity_extractor()
    
    for test_case in test_cases:
        print(f"\n{'='*60}")
        print(f"Input: '{test_case}'")
        print(f"{'='*60}")
        result = extractor.get_filtered_data(test_case)
        print(f"Message: {result.get('message', 'No message')}")
        print(f"Summary: {result.get('summary', {})}")
        if result.get('entities_found'):
            print(f"Entities: {result['entities_found']}")
        print("-" * 60)