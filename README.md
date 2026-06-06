# Global Semiconductor Trade Flows

An interactive arc map visualising integrated circuit (HS 8542) exports from the world's major semiconductor-producing nations from 2018 to 2024.

Built with Python, UN Comtrade API, and Streamlit.

## What it shows

Global semiconductor export flows from Taiwan, South Korea, China, the Netherlands, the USA, and Japan — animated by year using a slider. Arc width is proportional to export value. The 2022 inflection point reflects the impact of US export controls on advanced chip exports to China.

## Data source

UN Comtrade Database — Merchandise Trade Statistics (HS 8542: Electronic integrated circuits)
[comtradeplus.un.org](https://comtradeplus.un.org)

## Tech stack

- **Data**: UN Comtrade API via `comtradeapicall`
- **Processing**: `pandas`
- **Visualisation**: `pydeck` ArcLayer on Carto dark basemap
- **Deployment**: Streamlit Cloud

## Local setup

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Add your UN Comtrade subscription key to `.streamlit/secrets.toml`:
   ```toml
   COMTRADE_KEY = "your-key-here"
   ```
4. Run the app:
   ```
   streamlit run app.py
   ```

## Deployment

Deployed on Streamlit Cloud. The `COMTRADE_KEY` secret is configured via the Streamlit Cloud dashboard under Settings > Secrets and is never stored in the repository.

## Author

Ng Ka Wai — [linkedin.com/in/ngkawaix](https://linkedin.com/in/ngkawaix)
