import os
import pandas as pd
import numpy as np
from scipy import stats
from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from crewai_tools import BaseTool
from typing import ClassVar, List, Dict, Any

class PriceEstimatorTool(BaseTool):
    name: str = "PriceEstimatorTool"
    description: str = (
        "Generates keyword ideas using Google Ads API and estimates CPC and CPA based on keyword search volume. "
        "Takes a list of keywords as input and returns analysis results."
    )

    def _run(self, keywords: str, location_id="2840", language_code="1000") -> Dict[str, Any]:
        """
        Executes the price estimation tool by generating keyword ideas and analyzing CPC/CPA metrics.
        :param keywords: Comma-separated string of keywords to analyze
        :param location_id: Location ID (default: "2840" for USA)
        :param language_code: Language code (default: "1000" for English)
        :return: A dictionary with the analyzed keyword data
        """
        try:
            # Initialize KeywordPlanner
            planner = KeywordPlanner()
            
            # Get keyword ideas from Google Ads API
            keyword_data = planner.get_keyword_ideas(keywords, location_id, language_code)

            if keyword_data.empty:
                return {"error": "No keyword ideas were generated."}

            # Save the keyword data to a CSV (optional)
            csv_file = "crew_io_files/keyword_data_pre_analysis.csv"
            keyword_data.to_csv(csv_file, index=False)
            print(f"Keyword data saved to {csv_file}.")

            # Analyze the keyword data
            analyzer = KeywordAnalyzer(keyword_data)
            analysis_result = analyzer.analyze()

            return {
                "csv_file": csv_file,
                "analysis": analysis_result
            }

        except Exception as e:
            return {"error": f"An error occurred: {str(e)}"}


class KeywordPlanner:
    def __init__(self):
        load_dotenv()
        self.client = GoogleAdsClient.load_from_env()
        self.customer_id = os.getenv("GOOGLE_ADS_CUSTOMER_ID")
        
    def map_location_id_to_resource_name(self, location_id):
        geo_service = self.client.get_service("GeoTargetConstantService")
        return [geo_service.geo_target_constant_path(location_id)]
    
    def get_keyword_ideas(self, keywords, location_id="2840", language_code="1000"):
        if isinstance(keywords, str):
            keywords = [keyword.strip() for keyword in keywords.split(",")]

        keyword_plan_idea_service = self.client.get_service("KeywordPlanIdeaService")
        keyword_plan_network = self.client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH_AND_PARTNERS

        location_rns = self.map_location_id_to_resource_name(location_id)
        language_rn = f'languageConstants/{language_code}'
        
        request = self.client.get_type("GenerateKeywordIdeasRequest")
        request.customer_id = self.customer_id
        request.language = language_rn
        request.geo_target_constants = location_rns
        request.include_adult_keywords = False
        request.keyword_plan_network = keyword_plan_network

        keyword_seed = self.client.get_type("KeywordSeed")
        for keyword in keywords:
            keyword_seed.keywords.append(keyword)
        request.keyword_seed = keyword_seed

        try:
            response = keyword_plan_idea_service.generate_keyword_ideas(request=request)
            keyword_ideas = [
                {
                    "keyword": idea.text,
                    "avg_monthly_searches": idea.keyword_idea_metrics.avg_monthly_searches,
                    "competition_index": idea.keyword_idea_metrics.competition.name,
                    "cpc_low": idea.keyword_idea_metrics.low_top_of_page_bid_micros / 1e6,
                    "cpc_high": idea.keyword_idea_metrics.high_top_of_page_bid_micros / 1e6,
                }
                for idea in response
            ]
            return pd.DataFrame(keyword_ideas)
        except GoogleAdsException as ex:
            print(f'Request with ID "{ex.request_id}" failed with status "{ex.error.code().name}".')
            for error in ex.failure.errors:
                print(f'\tError: "{error.message}".')
            raise


class KeywordAnalyzer:
    def __init__(self, data: pd.DataFrame):
        self.df = data

    def analyze(self):
        # Convert numeric columns to appropriate data types
        numeric_cols = ['avg_monthly_searches', 'competition_index', 'cpc_low', 'cpc_high']
        for col in numeric_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')

        # Calculate average CPC and confidence interval
        self.df['avg_cpc'] = (self.df['cpc_low'] + self.df['cpc_high']) / 2
        self.df['cpc_std'] = (self.df['cpc_high'] - self.df['cpc_low']) / 4  # Assuming 95% of data falls between low and high

        # Set click-to-applicant ratio
        click_to_applicant_ratio = 0.08

        # Calculate CPA and its confidence interval
        self.df['cpa'] = self.df['avg_cpc'] / click_to_applicant_ratio
        self.df['cpa_std'] = self.df['cpc_std'] / click_to_applicant_ratio

        # Function to calculate confidence interval
        def conf_interval(mean, std, conf=0.95):
            if pd.isna(mean) or pd.isna(std) or std == 0:
                return (mean, mean)
            return stats.norm.interval(conf, loc=mean, scale=std)

        # Calculate CPC and CPA ranges
        self.df['cpc_lower'], self.df['cpc_upper'] = zip(*self.df.apply(lambda row: conf_interval(row['avg_cpc'], row['cpc_std']), axis=1))
        self.df['cpa_lower'], self.df['cpa_upper'] = zip(*self.df.apply(lambda row: conf_interval(row['cpa'], row['cpa_std']), axis=1))

        # Calculate overall statistics
        avg_cpc = self.df['avg_cpc'].mean()
        avg_cpa = self.df['cpa'].mean()
        cpc_lower_mean = self.df['cpc_lower'].mean()
        cpc_upper_mean = self.df['cpc_upper'].mean()
        cpa_lower_mean = self.df['cpa_lower'].mean()
        cpa_upper_mean = self.df['cpa_upper'].mean()

        # Calculate weighted averages
        total_searches = self.df['avg_monthly_searches'].sum()
        weighted_avg_cpc = (self.df['avg_cpc'] * self.df['avg_monthly_searches']).sum() / total_searches
        weighted_avg_cpa = (self.df['cpa'] * self.df['avg_monthly_searches']).sum() / total_searches

        # Calculate weighted confidence intervals
        weighted_cpc_std = np.sqrt(((self.df['cpc_std']**2) * (self.df['avg_monthly_searches']**2)).sum()) / total_searches
        weighted_cpa_std = weighted_cpc_std / click_to_applicant_ratio

        weighted_cpc_lower, weighted_cpc_upper = conf_interval(weighted_avg_cpc, weighted_cpc_std)
        weighted_cpa_lower, weighted_cpa_upper = conf_interval(weighted_avg_cpa, weighted_cpa_std)

        # Format results
        response = f"""
        Overall Statistics:
        Average CPC: ${avg_cpc:.2f} (95% CI: ${cpc_lower_mean:.2f} - ${cpc_upper_mean:.2f})
        Average CPA: ${avg_cpa:.2f} (95% CI: ${cpa_lower_mean:.2f} - ${cpa_upper_mean:.2f})

        Weighted Average CPC: ${weighted_avg_cpc:.2f} (95% CI: ${weighted_cpc_lower:.2f} - ${weighted_cpc_upper:.2f})
        Weighted Average CPA: ${weighted_avg_cpa:.2f} (95% CI: ${weighted_cpa_lower:.2f} - ${weighted_cpa_upper:.2f})
        """

        # Return the formatted result as a dictionary (for structured output)
        return {
            "Overall Statistics": {
                "Average CPC": f"${avg_cpc:.2f} (95% CI: ${cpc_lower_mean:.2f} - ${cpc_upper_mean:.2f})",
                "Average CPA": f"${avg_cpa:.2f} (95% CI: ${cpa_lower_mean:.2f} - ${cpa_upper_mean:.2f})",
                "Weighted Average CPC": f"${weighted_avg_cpc:.2f} (95% CI: ${weighted_cpc_lower:.2f} - ${weighted_cpc_upper:.2f})",
                "Weighted Average CPA": f"${weighted_avg_cpa:.2f} (95% CI: ${weighted_cpa_lower:.2f} - ${weighted_cpa_upper:.2f})",
            }
        }


# Example of how an AI agent would call the tool
if __name__ == "__main__":
    tool = PriceEstimatorTool()
    response = tool._run("sales associate jobs, marketing jobs, product manager jobs")
    #print(response)
