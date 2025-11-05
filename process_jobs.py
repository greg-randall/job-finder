import os
import csv
import hashlib
import glob
from pathlib import Path
import argparse
import pandas as pd
from datetime import datetime
import time
import openai
from tqdm import tqdm
import time
import json
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from functools import lru_cache

# Import config loader
from config_loader import get_config, get_openai_api_key

# Load configuration
config = get_config()

# Get coordinates from config
location_config = config.get_location_config()
RICHMOND_COORDS = (
    location_config.get('coordinates', {}).get('latitude', 37.5407),
    location_config.get('coordinates', {}).get('longitude', -77.4360)
)

# Get OpenAI API key from environment variables via config
try:
    openai.api_key = get_openai_api_key()
except ValueError as e:
    # Fallback to old behavior if config not available
    openai.api_key = os.environ.get("OPENAI_API_KEY")
    if not openai.api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

def load_document(file_path):
    """Load a document from a file path."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error loading {file_path}: {str(e)}")
        return None

def get_completed_urls():
    """Get a set of URLs that have already been processed."""
    completed_urls = set()
    
    # Check if the completed URLs file exists
    urls_path = Path("completed_urls.txt")
    if urls_path.exists():
        try:
            with open(urls_path, 'r', encoding='utf-8') as file:
                for line in file:
                    url = line.strip()
                    if url:  # Skip empty lines
                        completed_urls.add(url)
            print(f"Found {len(completed_urls)} completed URLs")
        except Exception as e:
            print(f"Error reading completed URLs file: {str(e)}")
    
    return completed_urls

def add_completed_url(url):
    """Add a URL to the completed URLs file."""
    try:
        with open("completed_urls.txt", 'a', encoding='utf-8') as file:
            file.write(f"{url}\n")
    except Exception as e:
        print(f"Error adding URL to completed URLs file: {str(e)}")

def get_processed_jobs():
    """Get a set of cache files that have already been processed."""
    # This function is kept for backward compatibility but now just calls get_completed_urls
    completed_urls = get_completed_urls()
    return set(), completed_urls  # Return empty set for cache files and the completed URLs

def save_job_rating(job_url, job_title, company, location, overall_rating, 
                   experience_match, education_match, skills_match, interest_match,
                   remote_work, full_time, salary, deal_breakers, cache_file, csv_path):
    """Save job rating to CSV file with detailed match scores."""
    # Check if file exists to determine if we need to write headers
    file_exists = os.path.isfile(csv_path)
    
    # Convert deal_breakers to a properly escaped string
    if isinstance(deal_breakers, list):
        # Join with a character that's unlikely to be in the text
        deal_breakers_str = " | ".join(str(item).replace('"', '""').replace(',', '\\,') for item in deal_breakers)
    else:
        deal_breakers_str = str(deal_breakers).replace('"', '""').replace(',', '\\,')
    
    # Ensure all fields are properly escaped
    row_data = {
        'job_url': str(job_url).replace('"', '""'),
        'job_title': str(job_title).replace('"', '""'),
        'company': str(company).replace('"', '""'),
        'location': str(location).replace('"', '""'),
        'overall_rating': overall_rating,
        'experience_match': experience_match,
        'education_match': education_match,
        'skills_match': skills_match,
        'interest_match': interest_match,
        'remote_work': remote_work,
        'full_time': full_time,
        'salary': str(salary).replace('"', '""').replace(',', '\\,'),
        'deal_breakers': deal_breakers_str,
        'processed_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'cache_file': str(cache_file).replace('"', '""')
    }
    
    # Define the field names in the correct order
    fieldnames = [
        'job_url', 'job_title', 'company', 'location', 
        'overall_rating', 'experience_match', 'education_match', 
        'skills_match', 'interest_match',
        'remote_work', 'full_time', 'salary', 'deal_breakers', 'processed_date', 'cache_file'
    ]
    
    try:
        with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=fieldnames,
                quotechar='"',
                quoting=csv.QUOTE_ALL,  # Quote all fields
                escapechar='\\',        # Use backslash as escape character
                doublequote=True        # Double quotes within quoted fields
            )
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerow(row_data)
    except Exception as e:
        print(f"Error writing to CSV: {str(e)}")
        # Create a backup of the problematic row for debugging
        with open(f"{csv_path}.error_log", 'a', encoding='utf-8') as error_log:
            error_log.write(f"Error at {datetime.now()}: {str(e)}\n")
            error_log.write(f"Attempted to write row: {row_data}\n\n")


def rate_job_match(job_content, resume_content, cover_letter_content=None, weights=None, min_threshold=None):
    """
    Use OpenAI's GPT-4o-mini to rate how well a job matches a resume and optionally a cover letter
    with separate scores for different match categories. Uses a more critical evaluation approach.

    Args:
        job_content (str): The job description text
        resume_content (str): The resume text
        cover_letter_content (str, optional): The cover letter text. Defaults to None.
        weights (dict, optional): Custom weights for different match categories. Defaults to None.
        min_threshold (float, optional): Minimum threshold for considering a job. Defaults to None.
                                        If set, jobs below this threshold will return None.

    Returns:
        tuple: (overall_rating, experience_match, education_match, skills_match,
                interest_match, job_title, company, location, remote_work, salary, deal_breakers)
        or None if the job doesn't meet the minimum threshold
    """
    try:
        # Define the function schema for the API to follow
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "evaluate_job_match",
                    "description": "Critically evaluate how well a JOB DESCRIPTION matches a candidate's RESUME and COVER LETTER across multiple dimensions",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_title": {
                                "type": "string",
                                "description": "The title of the job"
                            },
                            "company": {
                                "type": "string",
                                "description": "The company offering the job"
                            },
                            "location": {
                                "type": "string",
                                "description": "The location of the job"
                            },
                            "remote_work": {
                                "type": "boolean",
                                "description": "Return TRUE only if the job is explicitly described as fully remote (100% remote, work from anywhere, fully virtual, telecommute, work from home). Return FALSE for hybrid roles, occasional remote work, partially remote, or if remote status is unclear or not mentioned. Look for specific phrases like 'fully remote,' 'remote position,' or 'work from home' that indicate a completely remote role. Default to FALSE unless the job posting clearly states it's a fully remote position."
                            },
                            "full_time": {
                                "type": "boolean",
                                "description": "Whether the job is full-time. If you can't determine if the job is full-time, reply with boolean true as default. This should be false only if the job explicitly states it's part-time, contract, or temporary."
                            },
                            "salary": {
                                "type": "string",
                                "description": "The salary or pay rate mentioned in the job description (e.g., '$69,000', '$44,000-$55,000', '$37.23/hr', or 'Unknown Pay' if not found or not numerically specified)"
                            },
                            "experience_match": {
                                "type": "integer",
                                "description": "Rating 1-10 of how well the candidate's work experience matches the job requirements. Be critical - a score of 10 should only be given for perfect matches. A score of 7 means good but not great. Score of 5 means barely acceptable."
                            },
                            "education_match": {
                                "type": "integer",
                                "description": "Rating 1-10 of how well the candidate's education matches the job requirements. Be critical - a score of 10 should only be given for perfect matches. A score of 7 means good but not great. Score of 5 means barely acceptable."
                            },
                            "skills_match": {
                                "type": "integer",
                                "description": "Rating 1-10 of how well the candidate's skills match the job requirements. Be critical - a score of 10 should only be given for perfect matches. A score of 7 means good but not great. Score of 5 means barely acceptable."
                            },
                            "interest_match": {
                                "type": "integer",
                                "description": "Rating 1-10 of how well the job aligns with the candidate's expressed interests and career goals. Be critical - a score of 10 should only be given for perfect matches. A score of 7 means good but not great. Score of 5 means barely acceptable."
                            },
                            "deal_breakers": {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                },
                                "description": "List specific requirements from the job that the candidate does NOT meet. These should be critical requirements that would likely disqualify the candidate. BE VERY CONCISE 3-23 words!!! If none, return an empty array."
                            }
                        },
                        "required": [
                            "job_title", "company", "location", "remote_work", "full_time", "salary",
                            "experience_match", "education_match", "skills_match", 
                            "interest_match", "deal_breakers"
                        ]
                    }
                }
            }
        ]

        # Prepare the prompt for GPT with stricter evaluation criteria
        cover_letter_section = f"\nCOVER LETTER:\n{cover_letter_content}\n" if cover_letter_content else ""
        interest_guidance = "Based on the cover letter and resume" if cover_letter_content else "Based on the resume"

        prompt = f"""
RESUME:
{resume_content}
{cover_letter_section}
JOB DESCRIPTION:
{job_content}

Critically evaluate how well this job matches the candidate's qualifications.
Be STRICT and REALISTIC in your assessment. Do NOT be generous with scores.

Focus on these key areas:
1. Experience: Does the candidate TRULY have the REQUIRED years and type of work experience?
2. Education: Does the candidate EXACTLY meet the educational requirements?
3. Skills: Does the candidate DEMONSTRABLY possess the technical and soft skills required?
4. Interest: {interest_guidance}, how HONESTLY well does this align with the candidate's interests?

For each area, provide a score from 1-10, using this critical scale:
- 10: Perfect match, candidate exceeds all requirements
- 8-9: Strong match, meets almost all requirements with relevant experience
- 7: Good match, meets most key requirements
- 5-6: Average match, meets some requirements but has notable gaps
- 3-4: Weak match, missing several important requirements
- 1-2: Poor match, candidate lacks most required qualifications

Also identify any deal-breakers - specific requirements the candidate does not meet that would likely disqualify them.

DO NOT inflate scores. Be realistic about the job market's competitiveness.
A truly good match should be rare.
"""

        # Call the OpenAI API with function calling
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a critical job application assistant that realistically evaluates job matches. You should be strict, not generous."},
                {"role": "user", "content": prompt}
            ],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "evaluate_job_match"}},
            temperature=0.2  # Lower temperature for more consistent, critical evaluations
        )
        
        # Extract the function call arguments
        function_call = response.choices[0].message.tool_calls[0].function
        result = json.loads(function_call.arguments)
        
        # Extract the fields with defaults if missing
        job_title = result.get('job_title', 'Unknown Title')
        company = result.get('company', 'Unknown Company')
        location = result.get('location', 'Unknown Location')
        remote_work = result.get('remote_work', False)
        full_time = result.get('full_time', True)  # Default to True if not specified
        salary = result.get('salary', 'Unknown Pay')
        deal_breakers = result.get('deal_breakers', [])
        
        # Extract the match ratings with defaults
        experience_match = result.get('experience_match', 0)
        education_match = result.get('education_match', 0)
        skills_match = result.get('skills_match', 0)
        interest_match = result.get('interest_match', 0)
        
        # Use provided weights or default to prioritize experience and skills
        if weights is None:
            weights = {
                'experience_match': 0.35,  # Increased weight for experience
                'education_match': 0.15,   # Decreased weight for education
                'skills_match': 0.35,      # Increased weight for skills
                'interest_match': 0.15     # Decreased weight for interest
            }
        
        overall_rating = round(
            weights['experience_match'] * experience_match +
            weights['education_match'] * education_match +
            weights['skills_match'] * skills_match +
            weights['interest_match'] * interest_match,
            1  # Round to 1 decimal place
        )
        
        # Apply the minimum threshold filter if specified
        if min_threshold is not None and (overall_rating < min_threshold or len(deal_breakers) > 0):
            return None  # Return None for jobs that don't meet the threshold or have deal breakers
        
        return (overall_rating, experience_match, education_match, 
                skills_match, interest_match,
                job_title, company, location, remote_work, full_time, salary, deal_breakers)
        
    except Exception as e:
        print(f"Error calling OpenAI API: {str(e)}")
        # Return None for errors
        return None

@lru_cache(maxsize=1000)
def geocode_location(location_str, timeout=1):
    """Geocode a location string and return coordinates."""
    geolocator = Nominatim(user_agent="location_checker")
    try:
        result = geolocator.geocode(location_str, timeout=timeout)
        if result:
            return (result.latitude, result.longitude)
        return None
    except Exception as e:
        print(f"Error geocoding {location_str}: {e}")
        return None

def is_near_richmond(location, radius_miles=50):
    """
    Check if a location is within specified radius of Richmond, Virginia.
    
    Args:
        location (str): The location string to check
        radius_miles (float): Maximum distance in miles (default: 50 miles)
        
    Returns:
        bool: True if the location is within the specified radius of Richmond, False otherwise
    """
    if not location or isinstance(location, float):  # Handle None or NaN values
        return False
    
    location_str = str(location).lower()
    
    # Quick check for obvious Richmond area mentions
    richmond_area_terms = [
        'richmond', 'glen allen', 'mechanicsville', 'chester', 'chesterfield',
        'midlothian', 'henrico', 'ashland', 'colonial heights', 'hopewell',
        'petersburg', 'hanover', 'goochland', 'powhatan', 'dinwiddie'
    ]
    
    for term in richmond_area_terms:
        if term in location_str:
            return True
    
    # Only proceed with geocoding if the location is likely in Virginia
    virginia_indicators = [
        'va', 'virginia',
        '232', '231', '238', # Richmond area zipcodes
    ]
    
    is_in_virginia = False
    for indicator in virginia_indicators:
        if indicator in location_str:
            is_in_virginia = True
            break
    
    if not is_in_virginia:
        return False  # Skip geocoding for non-Virginia locations
    
    # Convert miles to kilometers
    radius_km = radius_miles * 1.60934
    
    # Geocode the location
    coords = geocode_location(location_str)
    
    if not coords:
        # Try adding Virginia if it might help
        if 'va' not in location_str and 'virginia' not in location_str:
            virginia_location = f"{location_str}, virginia"
            coords = geocode_location(virginia_location)
    
    if coords:
        distance = geodesic(RICHMOND_COORDS, coords).kilometers
        return distance <= radius_km
    
    return False


def should_skip_job_url(job_url):
    """
    Check if a job URL should be skipped based on filtering rules.
    
    Args:
        job_url: The job URL to check
        
    Returns:
        bool: True if the job should be skipped, False otherwise
    """
    import re
    
    # Skip pagination pages from rejobs.org
    if "rejobs.org" in job_url and re.search(r"[?&]page=\d+", job_url):
        return True
    
    # Skip URLs with /location/ in them from rejobs.org as they're typically listing pages
    if "rejobs.org" in job_url and "/location/" in job_url:
        return True
        
    return False

def has_sufficient_content(job_content, min_length=200):
    """
    Check if a job description has sufficient content to be properly evaluated.
    
    Args:
        job_content (str): The job description content
        min_length (int): Minimum character length required (default: 200)
        
    Returns:
        bool: True if the job has sufficient content, False otherwise
    """
    if not job_content:
        return False
        
    # Split by lines to get the actual job description (skip the URL line)
    content_lines = job_content.strip().split('\n')
    
    # If there's only one line (the URL), it's definitely too short
    if len(content_lines) <= 1:
        return False
        
    # Skip the first line (URL) and join the rest
    actual_content = '\n'.join(content_lines[1:])
    
    # Check if the content is too short
    return len(actual_content) >= min_length

def process_jobs(resume_path, cover_letter_path=None, max_jobs=None, debug=False, force_reprocess=False, parallel=8, weights=None):
    """
    Process jobs from the cache folder, compare them to the resume and optionally a cover letter,
    and rate how well they match with detailed category scores.

    Args:
        resume_path: Path to the resume file
        cover_letter_path: Path to the cover letter file (optional)
        max_jobs: Maximum number of jobs to process (None for all)
        debug: Enable debug output
        force_reprocess: Force reprocessing of already processed jobs
        parallel: Number of parallel processes to use
    """
    # Load resume and cover letter
    resume_content = load_document(resume_path)
    cover_letter_content = load_document(cover_letter_path) if cover_letter_path else None

    if not resume_content:
        print("Error: Could not load resume")
        return

    if cover_letter_path and not cover_letter_content:
        print("Warning: Cover letter path provided but could not load cover letter. Continuing without it.")
        cover_letter_content = None
    
    # Get already processed URLs
    completed_urls = get_completed_urls() if not force_reprocess else set()
    print(f"Found {len(completed_urls)} already processed URLs")
    
    # Get all cached job files
    cache_dir = Path("cache")
    if not cache_dir.exists():
        print(f"Error: Cache directory '{cache_dir}' does not exist")
        return
    
    job_files = list(cache_dir.glob("*.txt"))
    print(f"Found {len(job_files)} cached job files")
    
    # Path for the output CSV
    csv_path = Path("processed_jobs.csv")
    
    # Get all job files and their content
    jobs_to_process = []
    for job_file in job_files:
        job_content = load_document(job_file)
        if not job_content:
            continue
        
        # Extract job URL from the first line of the content
        job_url = job_content.strip().split('\n')[0] if job_content else "Unknown"
        
        # Strip quotes from URL if present
        job_url = job_url.strip('"\'')
        
        # Skip if already processed and not forcing reprocessing
        if not force_reprocess and job_url in completed_urls:
            if debug:
                print(f"Skipping already processed job URL: {job_url}")
            continue
        
        # Skip jobs that match filtering rules
        if should_skip_job_url(job_url):
            if debug:
                print(f"Skipping job with filtered URL: {job_url}")
            continue
    
        # Skip jobs with insufficient content
        if not has_sufficient_content(job_content, min_length=200):
            if debug:
                print(f"Skipping job with insufficient content: {job_url}")
            continue
            
        jobs_to_process.append((job_file, job_content, job_url))
    
    # For debug mode, randomly select jobs and show samples
    if debug:
        import random
        if len(jobs_to_process) > 100:
            jobs_to_process = random.sample(jobs_to_process, 100)
        print(f"Processing {len(jobs_to_process)} randomly selected jobs")
        
        # Sample a few processed jobs to check URL format
        sample_size = min(5, len(completed_urls))
        if sample_size > 0:
            print("\nSample of processed URLs:")
            for url in list(completed_urls)[:sample_size]:
                print(f"  - {repr(url)}")
        
        # Sample a few job files to check URL extraction
        sample_size = min(5, len(job_files))
        if sample_size > 0:
            print("\nSample of job file URLs:")
            for job_file in job_files[:sample_size]:
                content = load_document(job_file)
                if content:
                    url = content.strip().split('\n')[0]
                    print(f"  - File: {job_file}")
                    print(f"    URL: {repr(url)}")
    else:
        print(f"Processing {len(jobs_to_process)} jobs")
    
    # Limit the number of jobs to process if specified
    if max_jobs is not None and max_jobs < len(jobs_to_process):
        import random
        random.shuffle(jobs_to_process)  # Randomize the list
        jobs_to_process = jobs_to_process[:max_jobs]
        print(f"Limited to processing {max_jobs} randomly selected jobs")
    
    # Define a function to process a single job
    def process_single_job(job_data):
        job_file, job_content, job_url = job_data
        
        if debug:
            print(f"\nProcessing job: {job_url}")
        
        # Rate the job match with detailed category scores
        result = rate_job_match(
            job_content, resume_content, cover_letter_content, weights
        )
        
        # Add the URL to completed URLs regardless of match result
        add_completed_url(job_url)
        
        # Skip if the job didn't meet criteria
        if result is None:
            if debug:
                print(f"Job did not meet minimum criteria: {job_url}")
            return None
            
        # Unpack the result
        (overall_rating, experience_match, education_match, 
         skills_match, interest_match,
         job_title, company, location, remote_work, full_time, salary, deal_breakers) = result
        
        # Return the results
        return {
            'job_file': job_file,
            'job_url': job_url,
            'job_title': job_title,
            'company': company,
            'location': location,
            'overall_rating': overall_rating,
            'experience_match': experience_match,
            'education_match': education_match,
            'skills_match': skills_match,
            'interest_match': interest_match,
            'remote_work': remote_work,
            'full_time': full_time,
            'salary': salary,
            'deal_breakers': deal_breakers
        }
    
    # Process jobs in parallel
    results = []
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        # Submit all jobs to the executor
        future_to_job = {executor.submit(process_single_job, job_data): job_data for job_data in jobs_to_process}
        
        # Process results as they complete
        for future in tqdm(concurrent.futures.as_completed(future_to_job), total=len(jobs_to_process), desc="Processing jobs"):
            job_data = future_to_job[future]
            try:
                result = future.result()
                
                # Skip if the job didn't meet criteria
                if result is None:
                    continue
                    
                results.append(result)
                
                # Save the result to CSV
                job_file = result['job_file']
                job_url = result['job_url']
                job_title = result['job_title']
                company = result['company']
                location = result['location']
                overall_rating = result['overall_rating']
                experience_match = result['experience_match']
                education_match = result['education_match']
                skills_match = result['skills_match']
                interest_match = result['interest_match']
                remote_work = result['remote_work']
                full_time = result['full_time']
                salary = result['salary']
                deal_breakers = result.get('deal_breakers', [])  # Get deal_breakers or default to empty list
                
                # Save to CSV
                cache_file = str(job_file)
                save_job_rating(
                    job_url, job_title, company, location, overall_rating,
                    experience_match, education_match, skills_match, interest_match,
                    "Yes" if remote_work else "No", "Yes" if full_time else "No", 
                    salary, deal_breakers, cache_file, csv_path
                )
                
                if debug:
                    print(f"Job: {job_title} at {company}")
                    print(f"Location: {location}")
                    print(f"Remote Work: {'Yes' if remote_work else 'No'}")
                    print(f"Full Time: {'Yes' if full_time else 'No'}")
                    print(f"Salary: {salary}")
                    print(f"Overall Rating: {overall_rating}/10")
                    print(f"Experience Match: {experience_match}/10")
                    print(f"Education Match: {education_match}/10")
                    print(f"Skills Match: {skills_match}/10")
                    print(f"Interest Match: {interest_match}/10")
                    print(f"URL: {job_url}")
                    print(f"Cache file: {job_file}")
                
            except Exception as e:
                print(f"Error processing job {job_data[2]}: {str(e)}")
    
    # Touch the processed_jobs.csv file to update its timestamp
    Path(csv_path).touch()
    
    print(f"\nProcessed {len(jobs_to_process)} jobs")
    print(f"Results saved to processed_jobs.csv")
    
    return results


# Function to create filtered and ranked job lists
def create_ranked_job_lists(csv_path, high_quality_threshold=7, min_category_score=None, weights=None, richmond_or_remote_only=True):
    """
    Create two ranked job lists: all jobs and high-quality matches.
    
    Args:
        csv_path: Path to the processed jobs CSV
        high_quality_threshold: Minimum overall rating to be considered high quality (default: 7)
        min_category_score: Minimum score required for each category (experience, education, skills, interest)
                           to be considered a high-quality match. If None, no minimum is applied.
        weights: Dictionary with weights for each category
                 If None, use equal weights
        richmond_or_remote_only: If True, only include jobs that are remote or within 50 miles of Richmond
    
    Returns:
        tuple: (all_jobs_df, high_quality_df) - DataFrames with all jobs and high-quality jobs
    """
    # Read the CSV with more flexible parsing to handle inconsistencies
    try:
        # Try with improved settings first
        df = pd.read_csv(csv_path, quotechar='"', escapechar='\\')
    except Exception as e:
        print(f"Error reading CSV with standard parser: {str(e)}")
        print("Trying with more flexible parsing settings...")
        # Try with even more flexible parsing settings
        try:
            # Add error_bad_lines=False to skip problematic rows
            df = pd.read_csv(csv_path, on_bad_lines='skip', engine='python', quotechar='"', escapechar='\\')
        except Exception as e2:
            print(f"Error with flexible parsing: {str(e2)}")
            print("Trying with maximum flexibility...")
            # Last resort - read with maximum flexibility
            df = pd.read_csv(csv_path, on_bad_lines='skip', engine='python', quoting=3)  # quoting=3 means QUOTE_NONE
    
    # Print column count to help diagnose issues
    print(f"CSV loaded with {len(df.columns)} columns: {df.columns.tolist()}")
    
    # Filter out jobs that should be skipped based on URL
    filtered_df = df.copy()
    filtered_df = filtered_df[~filtered_df['job_url'].apply(should_skip_job_url)]
    
    # Sort all jobs by overall rating
    all_jobs_df = filtered_df.sort_values('overall_rating', ascending=False)
    
    # Filter for high-quality matches
    high_quality_df = all_jobs_df[all_jobs_df['overall_rating'] >= high_quality_threshold]
    
    # Apply minimum category score filter if specified
    if min_category_score is not None:
        high_quality_df = high_quality_df[
            (high_quality_df['experience_match'] >= min_category_score) &
            (high_quality_df['education_match'] >= min_category_score) &
            (high_quality_df['skills_match'] >= min_category_score) &
            (high_quality_df['interest_match'] >= min_category_score)
        ]
    
    # Filter for full-time jobs only in high quality matches
    if 'full_time' in high_quality_df.columns:
        # Check the data type of the column
        if high_quality_df['full_time'].dtype == bool:
            # Handle boolean values directly
            full_time_mask = high_quality_df['full_time']
        else:
            # Convert to string first to safely use .str methods
            full_time_mask = high_quality_df['full_time'].astype(str).str.lower().isin(['yes', 'true', '1'])
        
        high_quality_df = high_quality_df[full_time_mask]
    
    # Filter for remote jobs or jobs near Richmond if specified
    if richmond_or_remote_only:
        # Convert remote_work column to boolean-like values
        remote_mask = high_quality_df['remote_work'].str.lower().isin(['yes', 'true', '1']) if 'remote_work' in high_quality_df.columns else False
        
        # Check if location is near Richmond
        near_richmond_mask = high_quality_df['location'].apply(is_near_richmond) if 'location' in high_quality_df.columns else False
        
        # Apply the combined filter
        high_quality_df = high_quality_df[remote_mask | near_richmond_mask]
    
    return all_jobs_df, high_quality_df


def fix_csv_file(csv_path):
    """Fix a CSV file with inconsistent number of fields."""
    import shutil
    from io import StringIO
    
    # Create a backup
    backup_path = f"{csv_path}.bak.{int(time.time())}"
    shutil.copy2(csv_path, backup_path)
    print(f"Created backup at {backup_path}")
    
    # Define the expected fields based on our code
    expected_fields = 15  # We know we should have 15 fields
    expected_fieldnames = [
        'job_url', 'job_title', 'company', 'location', 
        'overall_rating', 'experience_match', 'education_match', 
        'skills_match', 'interest_match',
        'remote_work', 'full_time', 'salary', 'deal_breakers', 'processed_date', 'cache_file'
    ]
    
    # Read the file line by line to identify and fix problematic rows
    fixed_lines = []
    problem_lines = []
    
    with open(csv_path, 'r', encoding='utf-8') as file:
        # Read the header
        header = file.readline().strip()
        
        # Check if the header has the correct number of fields
        header_fields = header.count(',') + 1
        if header_fields != expected_fields:
            print(f"WARNING: Header has {header_fields} fields, but we expect {expected_fields} fields")
            print(f"Header: {header}")
            # Use our expected fieldnames instead
            header = ','.join([f'"{field}"' for field in expected_fieldnames])
            print(f"Using corrected header: {header}")
        
        fixed_lines.append(header)
        
        # Process each line
        for i, line in enumerate(file, 2):  # Start at line 2 (after header)
            # Count commas that are not within quotes
            in_quotes = False
            escaped = False
            field_count = 1  # Start with 1 field
            
            for char in line:
                if escaped:
                    escaped = False
                    continue
                    
                if char == '\\':
                    escaped = True
                elif char == '"' and not escaped:
                    in_quotes = not in_quotes
                elif char == ',' and not in_quotes:
                    field_count += 1
            
            # Check if the line has the correct number of fields
            if field_count != expected_fields:
                problem_lines.append((i, line, field_count))
                # Try to fix the line by ensuring all fields are properly quoted
                try:
                    # Parse the line using csv module
                    reader = csv.reader(StringIO(line), quotechar='"', escapechar='\\', doublequote=True)
                    fields = next(reader)
                    
                    # If we have too many fields, combine extra fields into the deal_breakers field
                    if len(fields) > expected_fields:
                        # Assuming deal_breakers is the 13th field (index 12)
                        deal_breaker_index = 12
                        # Combine the extra fields with the deal_breakers field
                        combined_deal_breakers = fields[deal_breaker_index]
                        for j in range(deal_breaker_index + 1, len(fields) - (expected_fields - deal_breaker_index - 1)):
                            combined_deal_breakers += f" | {fields[j]}"
                        
                        # Reconstruct the fields list with the combined deal_breakers
                        new_fields = fields[:deal_breaker_index] + [combined_deal_breakers] + fields[-(expected_fields - deal_breaker_index - 1):]
                        fields = new_fields
                    
                    # If we have too few fields, add empty fields
                    while len(fields) < expected_fields:
                        fields.append("")
                    
                    # Write the fields back to a CSV string
                    output = StringIO()
                    writer = csv.writer(output, quotechar='"', escapechar='\\', 
                                       quoting=csv.QUOTE_ALL, doublequote=True)
                    writer.writerow(fields)
                    fixed_line = output.getvalue().strip()
                    fixed_lines.append(fixed_line)
                    print(f"Fixed line {i}: {field_count} fields -> {expected_fields} fields")
                except Exception as e:
                    print(f"Could not fix line {i}: {str(e)}")
                    # Add a comment marker to the line so it's ignored
                    fixed_lines.append(f"# ERROR in line {i}: {line}")
            else:
                fixed_lines.append(line.strip())
    
    # Write the fixed content back to a new file
    fixed_path = f"{csv_path}.fixed"
    with open(fixed_path, 'w', encoding='utf-8') as file:
        for line in fixed_lines:
            file.write(line + '\n')
    
    print(f"Fixed CSV saved to {fixed_path}")
    print(f"Found {len(problem_lines)} problematic lines")
    
    # Write problem lines to a separate file for inspection
    if problem_lines:
        with open(f"{csv_path}.problems", 'w', encoding='utf-8') as file:
            for line_num, content, field_count in problem_lines:
                file.write(f"Line {line_num} (fields: {field_count}):\n{content}\n\n")
        print(f"Problematic lines saved to {csv_path}.problems for inspection")
    
    return fixed_path

def repair_processed_jobs_csv(csv_path):
    """Repair the processed jobs CSV by normalizing URLs and removing duplicates."""
    import shutil
    
    try:
        # Create backup before doing anything
        backup_path = f"{csv_path}.bak"
        shutil.copy2(csv_path, backup_path)
        print(f"Created backup at {backup_path}")
        
        # Define the expected columns
        expected_columns = [
            'job_url', 'job_title', 'company', 'location', 
            'overall_rating', 'experience_match', 'education_match', 
            'skills_match', 'interest_match',
            'remote_work', 'full_time', 'salary', 'deal_breakers', 'processed_date', 'cache_file'
        ]
        print(f"Expected {len(expected_columns)} columns: {expected_columns}")
        
        # First, try to read the file as raw text to examine its structure
        with open(csv_path, 'r', encoding='utf-8') as f:
            first_few_lines = [next(f) for _ in range(5)]  # Read first 5 lines
        
        print("First few lines of the CSV:")
        for i, line in enumerate(first_few_lines):
            print(f"Line {i+1}: {line.strip()}")
            if i == 0:  # Header line
                header_fields = line.count(',') + 1
                print(f"Header has {header_fields} fields (expected {len(expected_columns)})")
        
        # Read the CSV with flexible parsing
        try:
            # First attempt with standard settings
            df = pd.read_csv(csv_path, quotechar='"', escapechar='\\')
        except Exception as e:
            print(f"Warning: Standard CSV parsing failed: {str(e)}")
            try:
                # Second attempt with more flexible settings
                df = pd.read_csv(csv_path, on_bad_lines='skip', engine='python', quotechar='"', escapechar='\\')
            except Exception as e2:
                print(f"Warning: Flexible CSV parsing failed: {str(e2)}")
                # Last resort - read with maximum flexibility
                df = pd.read_csv(csv_path, on_bad_lines='skip', engine='python', quoting=3)  # QUOTE_NONE
        
        # Print the columns we found
        print(f"Found {len(df.columns)} columns: {df.columns.tolist()}")
        
        # If we don't have the right number of columns, try to fix it
        if len(df.columns) != len(expected_columns):
            print(f"WARNING: Found {len(df.columns)} columns, expected {len(expected_columns)}")
            
            # If we have too few columns, add missing ones
            for col in expected_columns:
                if col not in df.columns:
                    print(f"Adding missing column: {col}")
                    df[col] = ""
            
            # Make sure columns are in the right order
            df = df[expected_columns]
        
        # Check if job_url is missing
        if 'job_url' not in df.columns:
            print("WARNING: 'job_url' column is missing!")
            
            # If the first column doesn't have a name, it might be the job_url
            if df.columns[0] == 'Unnamed: 0' or df.columns[0].startswith('Unnamed:'):
                print(f"Found unnamed first column. Renaming to 'job_url'")
                df = df.rename(columns={df.columns[0]: 'job_url'})
            
            # If we still don't have job_url, try to extract from the first column's values
            if 'job_url' not in df.columns:
                # Check if the first column contains URLs
                first_col = df.iloc[:, 0]
                if first_col.str.contains('http').any():
                    print(f"First column appears to contain URLs. Renaming to 'job_url'")
                    df = df.rename(columns={df.columns[0]: 'job_url'})
        
        # Clean up URLs if the column exists
        if 'job_url' in df.columns:
            # Check if URLs need fixing
            sample_urls = df['job_url'].head(5).tolist()
            print(f"Sample URLs before cleaning: {sample_urls}")
            
            # Strip quotes from URLs
            df['job_url'] = df['job_url'].apply(lambda x: x.strip('"\'') if isinstance(x, str) else x)
            
            # Check if URLs were fixed
            sample_urls_after = df['job_url'].head(5).tolist()
            print(f"Sample URLs after cleaning: {sample_urls_after}")
        
        # Remove duplicates if job_url exists
        if 'job_url' in df.columns:
            before_count = len(df)
            df = df.drop_duplicates(subset=['job_url'])
            after_count = len(df)
            print(f"Removed {before_count - after_count} duplicate entries")
        
        # Save the repaired CSV
        repaired_path = f"{csv_path}.repaired"
        df.to_csv(repaired_path, index=False, quoting=csv.QUOTE_ALL)
        
        print(f"CSV repaired. Original backed up to {backup_path}, repaired version saved to {repaired_path}")
        print(f"Please check {repaired_path} to ensure it contains all the expected data before replacing the original.")
    except Exception as e:
        print(f"Error repairing CSV: {str(e)}")
        import traceback
        traceback.print_exc()

# Example usage in the main function
if __name__ == "__main__":
    # Get config defaults
    paths_config = config.get_paths_config()
    rating_config = config.get_rating_config()
    processing_config = config.get_processing_config()

    # Parse command-line arguments (with defaults from config)
    parser = argparse.ArgumentParser(description='Process job listings and rate them against a resume and optionally a cover letter')
    parser.add_argument('--resume', type=str, default=paths_config.get('resume', 'resume.md'), help='Path to the resume file')
    parser.add_argument('--cover-letter', type=str, default=paths_config.get('cover_letter'), help='Path to the cover letter file (optional)')
    parser.add_argument('--max-jobs', type=int, default=processing_config.get('max_jobs'), help='Maximum number of jobs to process')
    parser.add_argument('--debug', action='store_true', default=processing_config.get('debug', False), help='Enable debug output')
    parser.add_argument('--force', action='store_true', default=processing_config.get('force_reprocess', False), help='Force reprocessing of already processed jobs')
    parser.add_argument('--parallel', type=int, default=processing_config.get('parallel_workers', 32), help='Number of parallel requests to make')
    parser.add_argument('--repair-csv', action='store_true', help='Repair the processed_jobs.csv file to fix formatting issues')
    parser.add_argument('--fix-csv', action='store_true', help='Fix the processed_jobs.csv file to correct field count issues')
    parser.add_argument('--high-quality-threshold', type=float, default=rating_config.get('thresholds', {}).get('high_quality', 6.0), help='Threshold for high-quality matches (0-10)')
    parser.add_argument('--min-category-score', type=int, default=rating_config.get('thresholds', {}).get('min_category_score', 5), help='Minimum score required for each category')
    parser.add_argument('--exp-weight', type=float, default=rating_config.get('weights', {}).get('experience', 0.35), help='Weight for experience match (0-1)')
    parser.add_argument('--edu-weight', type=float, default=rating_config.get('weights', {}).get('education', 0.15), help='Weight for education match (0-1)')
    parser.add_argument('--skills-weight', type=float, default=rating_config.get('weights', {}).get('skills', 0.35), help='Weight for skills match (0-1)')
    parser.add_argument('--interest-weight', type=float, default=rating_config.get('weights', {}).get('interest', 0.15), help='Weight for interest match (0-1)')
    parser.add_argument('--all-locations', action='store_false', dest='richmond_or_remote_only',
                    help='Include all locations, not just remote or near Richmond')
    parser.set_defaults(richmond_or_remote_only=processing_config.get('richmond_or_remote_only', True))
    args = parser.parse_args()
    
    # Create weights dictionary from command line arguments
    weights = {
        'experience_match': args.exp_weight,
        'education_match': args.edu_weight,
        'skills_match': args.skills_weight,
        'interest_match': args.interest_weight
    }
    
    # Check if we should repair or fix the CSV
    if args.fix_csv:
        print("Fixing processed_jobs.csv file...")
        fixed_path = fix_csv_file('processed_jobs.csv')
        print(f"Fix complete. You can rename {fixed_path} to processed_jobs.csv if the fix was successful.")
        exit(0)
    elif args.repair_csv:
        print("Repairing processed_jobs.csv file...")
        repair_processed_jobs_csv('processed_jobs.csv')
        print("Repair complete. You can rename processed_jobs.csv.repaired to processed_jobs.csv if the repair was successful.")
        exit(0)
        
    # Process jobs and get results
    results = process_jobs(args.resume, args.cover_letter, args.max_jobs, args.debug, args.force, args.parallel, weights)
    
    # Create ranked job lists from all processed jobs
    all_jobs_df, all_high_quality_df = create_ranked_job_lists(
        'processed_jobs.csv',
        high_quality_threshold=args.high_quality_threshold,
        min_category_score=args.min_category_score,
        weights=weights,
        richmond_or_remote_only=args.richmond_or_remote_only
    )
    
    # Save all ranked jobs to a CSV
    all_jobs_csv_path = 'ranked_jobs.csv'
    all_jobs_df.to_csv(all_jobs_csv_path, index=False)
    print(f"\nAll ranked jobs saved to {all_jobs_csv_path}")
    
    # Get only the most recently processed jobs
    if len(results) > 0:
        # Create a DataFrame from the current processing run results
        current_results_df = pd.DataFrame(results)
        
        # Create high-quality matches from only the current run
        if 'overall_rating' in current_results_df.columns:
            # Filter for high-quality matches
            current_high_quality_df = current_results_df[current_results_df['overall_rating'] >= args.high_quality_threshold]
            
            # Apply minimum category score filter if specified
            if args.min_category_score is not None:
                current_high_quality_df = current_high_quality_df[
                    (current_high_quality_df['experience_match'] >= args.min_category_score) &
                    (current_high_quality_df['education_match'] >= args.min_category_score) &
                    (current_high_quality_df['skills_match'] >= args.min_category_score) &
                    (current_high_quality_df['interest_match'] >= args.min_category_score)
                ]
            
            # Filter for full-time jobs only
            if 'full_time' in current_high_quality_df.columns:
                # Check the data type of the column
                if current_high_quality_df['full_time'].dtype == bool:
                    # Handle boolean values directly
                    full_time_mask = current_high_quality_df['full_time']
                else:
                    # Convert to string first to safely use .str methods
                    full_time_mask = current_high_quality_df['full_time'].astype(str).str.lower().isin(['yes', 'true', '1'])
                
                current_high_quality_df = current_high_quality_df[full_time_mask]
            
            # Filter for remote jobs or jobs near Richmond if specified
            if args.richmond_or_remote_only:
                # Check if remote_work column exists
                if 'remote_work' in current_high_quality_df.columns:
                    # Check the data type of the column
                    if current_high_quality_df['remote_work'].dtype == bool:
                        # Handle boolean values directly
                        remote_mask = current_high_quality_df['remote_work']
                    else:
                        # Convert to string first to safely use .str methods
                        remote_mask = current_high_quality_df['remote_work'].astype(str).str.lower().isin(['yes', 'true', '1'])
                else:
                    remote_mask = pd.Series([False] * len(current_high_quality_df))

                near_richmond_mask = current_high_quality_df['location'].apply(is_near_richmond)
                current_high_quality_df = current_high_quality_df[remote_mask | near_richmond_mask]
            
            # Save high-quality matches to a separate CSV with timestamp only if we have matches
            if not current_high_quality_df.empty:
                current_time = datetime.now()
                timestamp = int(time.time())
                date_str = current_time.strftime('%B-%d-%Y').lower()
                time_str = current_time.strftime('%-I-%M%p').lower()
                high_quality_csv_path = f'high_quality_matches_{date_str}_{time_str}_{timestamp}.csv'
                current_high_quality_df.to_csv(high_quality_csv_path, index=False)
                print(f"High-quality matches from this run (rating ≥ {args.high_quality_threshold}) saved to {high_quality_csv_path}")
    
    # Only display high-quality jobs from the current run
    if len(results) > 0 and 'current_high_quality_df' in locals() and not current_high_quality_df.empty:
        print(f"\nTop high-quality matches from this run (found {len(current_high_quality_df)} matches):")
        for idx, job in current_high_quality_df.head(10).iterrows():
            print(f"{job['overall_rating']:.1f} - {job['job_title']} at {job['company']} ({job['location']})")
            print(f"  Experience: {job['experience_match']}/10 | Education: {job['education_match']}/10 | Skills: {job['skills_match']}/10 | Interest: {job['interest_match']}/10")
            print(f"  URL: {job['job_url']}")
            print()
    elif len(results) > 0:
        print(f"\nNo high-quality matches found in this run (rating ≥ {args.high_quality_threshold}).")