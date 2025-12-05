#!/usr/bin/env python3
"""
Asterisk AGI Script for Caller-ID Rotation
Place in /var/lib/asterisk/agi-bin/ on your Asterisk/VICIdial server
"""
import sys
import requests
import json
import logging
from typing import Dict, Optional

# Configure logging
logging.basicConfig(
    filename='/var/log/asterisk/callerid_rotation.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API Configuration
API_BASE_URL = 'http://127.0.0.1:8000'
API_TIMEOUT = 5  # seconds


class AGI:
    """Simple AGI interface"""
    
    def __init__(self):
        self.env = {}
        self._read_environment()
    
    def _read_environment(self):
        """Read AGI environment variables"""
        while True:
            line = sys.stdin.readline().strip()
            if not line:
                break
            key, _, value = line.partition(':')
            self.env[key.strip()] = value.strip()
        
        logger.debug(f"AGI Environment: {self.env}")
    
    def _send_command(self, command: str) -> str:
        """Send AGI command and get response"""
        print(command)
        sys.stdout.flush()
        response = sys.stdin.readline().strip()
        logger.debug(f"Command: {command}, Response: {response}")
        return response
    
    def verbose(self, message: str, level: int = 1):
        """Log verbose message"""
        self._send_command(f'VERBOSE "{message}" {level}')
    
    def set_variable(self, variable: str, value: str):
        """Set channel variable"""
        self._send_command(f'SET VARIABLE {variable} "{value}"')
    
    def get_variable(self, variable: str) -> Optional[str]:
        """Get channel variable"""
        response = self._send_command(f'GET VARIABLE {variable}')
        # Parse response: 200 result=1 (value)
        if '(' in response and ')' in response:
            return response.split('(')[1].split(')')[0]
        return None
    
    def exit(self):
        """Exit AGI script"""
        print('EXIT')
        sys.stdout.flush()


def get_next_caller_id(destination: str, campaign: str, agent: str) -> Optional[Dict]:
    """
    Call the Caller-ID Rotation API to get next available caller-ID
    """
    try:
        url = f"{API_BASE_URL}/next-cid"
        params = {
            'to': destination,
            'campaign': campaign,
            'agent': agent
        }
        
        logger.info(f"Requesting caller-ID for: to={destination}, campaign={campaign}, agent={agent}")
        
        response = requests.get(url, params=params, timeout=API_TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Success: Allocated caller-ID {data.get('caller_id')} for agent {agent}")
            return data
        else:
            logger.error(f"API error: {response.status_code} - {response.text}")
            return None
    
    except requests.exceptions.Timeout:
        logger.error(f"API request timeout after {API_TIMEOUT} seconds")
        return None
    
    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to API - is it running?")
        return None
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return None


def main():
    """Main AGI script execution"""
    agi = AGI()
    
    try:
        # Get parameters from AGI environment
        destination = agi.env.get('agi_extension', '')
        
        # Get campaign and agent from channel variables or arguments
        campaign = agi.env.get('agi_arg_1') or agi.get_variable('VICIDIAL_campaign') or 'default'
        agent = agi.env.get('agi_arg_2') or agi.get_variable('VICIDIAL_agent') or 'unknown'
        
        # Log the request
        agi.verbose(f"Caller-ID Rotation: Destination={destination}, Campaign={campaign}, Agent={agent}")
        logger.info(f"Processing request: destination={destination}, campaign={campaign}, agent={agent}")
        
        # Validate destination
        if not destination or len(destination) < 7:
            agi.verbose(f"Invalid destination: {destination}")
            logger.warning(f"Invalid destination: {destination}")
            agi.exit()
            return
        
        # Get next caller-ID from API
        result = get_next_caller_id(destination, campaign, agent)
        
        if result and result.get('success') and result.get('caller_id'):
            caller_id = result['caller_id']
            
            # Set the caller-ID
            agi.set_variable('CALLERID(num)', caller_id)
            agi.verbose(f"Set CallerID to: {caller_id}")
            
            # Store additional info in channel variables (optional)
            agi.set_variable('CALLERID_AREA_CODE', result.get('area_code', ''))
            agi.set_variable('CALLERID_CARRIER', result.get('carrier', ''))
            
            logger.info(f"Successfully set caller-ID to {caller_id} for agent {agent}")
        else:
            # API failed or no caller-ID available
            agi.verbose("Failed to get caller-ID from API - using default")
            logger.warning("API request failed or no caller-ID available - using default")
            
            # Optionally set a flag indicating fallback
            agi.set_variable('CALLERID_ROTATED', '0')
    
    except Exception as e:
        logger.error(f"AGI script error: {e}", exc_info=True)
        agi.verbose(f"Error in caller-ID rotation: {str(e)}")
    
    finally:
        agi.exit()


if __name__ == '__main__':
    main()
