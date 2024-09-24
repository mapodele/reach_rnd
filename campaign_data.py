import datetime
import os
import pandas as pd
import matplotlib.pyplot as plt
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
import re

# Load Google Ads client configuration
def load_google_ads_client(yaml_file_path):
    googleads_client = GoogleAdsClient.load_from_storage(yaml_file_path, version="v17")
    return googleads_client

# Extract city name from campaign name
def extract_city_name(campaign_name):
    match = re.search(r'delivery-partner-swiggy-in-(\w+)', campaign_name)
    if match:
        return match.group(1)
    return None

# Retrieve campaign performance data with daily budget
def get_campaign_performance(client, campaign_ids):
    google_ads_service = client.get_service("GoogleAdsService")
    customer_id = client.login_customer_id
    today = datetime.date.today()
    three_days_ago = today - datetime.timedelta(days=3)
    campaign_data = []

    for campaign_id in campaign_ids:
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                campaign_budget.amount_micros
            FROM campaign
            WHERE
                campaign.id = {campaign_id}
                AND segments.date BETWEEN '{three_days_ago}' AND '{today}'
        """

        search_request = client.get_type("SearchGoogleAdsStreamRequest")
        search_request.customer_id = customer_id
        search_request.query = query

        try:
            response = google_ads_service.search_stream(request=search_request)
            for batch in response:
                for row in batch.results:
                    campaign = row.campaign
                    metrics = row.metrics
                    budget_micros = row.campaign_budget.amount_micros  # Daily budget in micros
                    city_name = extract_city_name(campaign.name)
                    cost_inr = metrics.cost_micros / 1_000_000  # Cost in INR
                    cost_per_conversion = cost_inr / metrics.conversions if metrics.conversions > 0 else None
                    daily_budget_inr = budget_micros / 1_000_000  # Daily budget in INR
                    ctr = (metrics.clicks / metrics.impressions * 100) if metrics.impressions > 0 else None
                    cvr = (metrics.conversions / metrics.clicks * 100) if metrics.clicks > 0 else None
                    campaign_data.append({
                        'Campaign ID': campaign.id,
                        'City': city_name,
                        'Impressions': metrics.impressions,
                        'Clicks': metrics.clicks,
                        'Cost (INR)': cost_inr,  # Cost in INR
                        'Conversions': int(metrics.conversions),
                        'CPA': cost_per_conversion,
                        'CTR (%)': ctr,
                        'CVR (%)': cvr,
                        'Daily Budget (INR)': daily_budget_inr  # Daily Budget in INR
                    })
        except GoogleAdsException as ex:
            handle_googleads_exception(ex)

    df = pd.DataFrame(campaign_data)
    df['Cost (INR)'] = df['Cost (INR)'].round(2)
    df['CPA'] = df['CPA'].round(2)
    df['CTR (%)'] = df['CTR (%)'].round(2)
    df['CVR (%)'] = df['CVR (%)'].round(2)
    df['Daily Budget (INR)'] = df['Daily Budget (INR)'].round(2)
    return df

# Handle API errors
def handle_googleads_exception(exception):
    print(
        f'Request with ID "{exception.request_id}" failed with status '
        f'"{exception.error.code().name}" and includes the following errors:'
    )
    for error in exception.failure.errors:
        print(f'\tError with message "{error.message}".')
        if error.location:
            for field_path_element in error.location.field_path_elements:
                print(f"\t\tOn field: {field_path_element.field_name}")
    sys.exit(1)

# Bubble Chart for Cost (INR), CVR (%), and CPA
def plot_bubble_chart(df):
    plt.figure(figsize=(10, 6))
    
    # Create a scatter plot (bubble chart)
    plt.scatter(df['Cost (INR)'], df['CVR (%)'], s=df['CPA'] * 10, alpha=0.6, edgecolors="w", linewidth=2)

    # Add labels and title
    plt.title('Campaign Spend vs CVR with CPA as Bubble Size')
    plt.xlabel('Cost (INR)')
    plt.ylabel('CVR (%)')

    # Annotate each point with the city name
    for i in range(len(df)):
        plt.text(df['Cost (INR)'].iloc[i], df['CVR (%)'].iloc[i], df['City'].iloc[i], fontsize=9, ha='right')

    plt.grid(True)
    plt.show()

# Path to Google Ads YAML configuration
yaml_file_path = os.path.join(os.getcwd(), 'google-ads-india.yaml')

# Load Google Ads client
googleads_client = load_google_ads_client(yaml_file_path)

# List of campaign IDs
CAMPAIGN_IDS = [
    21655821328, 21652119722, 21652116959, 21652116422,
    21645505599, 21645497037, 21645495537, 21645495528,
    21645495525, 21633235582, 21629520710, 21620789456
]

# Retrieve performance data
df = get_campaign_performance(googleads_client, CAMPAIGN_IDS)

# Sort DataFrame by CVR (%) in descending order
df = df.sort_values(by='CVR (%)', ascending=False)

# Display the sorted DataFrame
df

# Plot the bubble chart for visualizing Cost (INR), CVR (%), and CPA
plot_bubble_chart(df)
