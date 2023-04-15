from tibia import Client, MarketValues, Wiki
import time
import os
import json
import schedule
import subprocess
from datetime import datetime
from git.repo import Repo


def write_marketable_items():
    items = Wiki().get_all_marketable_items()
    with open("tracked_items.txt", "w") as f:
        for item in items:
            f.write(item + "\n")

def write_events(results_location: str):
    """
    Writes all currently known events into the events.csv in the results_location.
    """
    try:
        last_date = datetime.min

        if os.path.exists(os.path.join(results_location, "events.csv")):
            with open(os.path.join(results_location, "events.csv"), "r") as event_file:
                previous_events = [event for event in event_file.readlines() if event and not str.isspace(event)]
                if previous_events:
                    last_date = datetime.strptime(previous_events[-1].split(",")[0], "%Y.%m.%d")

        with open(os.path.join(results_location, "events.csv"), "a+") as event_file:
            events = Wiki().get_events(last_date)
            if events:
                event_file.write("\n".join([event.__str__() for event in events]) + "\n")
    except Exception as e:
        print(f"Writing events failed: {e}")


def do_market_search(email: str, password: str, tibia_location: str, results_location: str):
    write_events(results_location)

    with open("tracked_items.txt", "r") as t:
        with open(os.path.join(results_location, "fullscan_tmp.csv"), "w+") as f:
            items = t.readlines()
            f.write("Name,SellPrice,BuyPrice,AvgSellPrice,AvgBuyPrice,Sold,Bought,Profit,RelProfit,PotProfit,ApproxOffers\n")
            
            client = Client(items)
            client.start_game(tibia_location)
            client.login_to_game(email, password)

            afk_time = time.time()
            fail_counter = 0
            retry_counter = 0
            
            if not client.open_market():
                client.exit_tibia()
                return
            
            client._find_memory_addresses()
            
            i = 0
            while i < len(items):
                item = items[i]
                
                # Restart Tibia every 13 minutes to avoid afk kick.
                if time.time() - afk_time > 800:
                    client.close_market()
                    client.wiggle()
                    afk_time = time.time()
                    client.open_market()

                values = client.search_item(item.replace("\n", ""))
                print(f"{i}. {values}")
                
                i += 1

                # Item search failed.
                if values.approx_offers == -1:
                    fail_counter += 1
                    
                    # If it failed 11 times in a row, reopen market and go back.
                    # Probably a disconnect.
                    if fail_counter == 11:
                        retry_counter += 1
                        if retry_counter >= 10:
                            print("Something is wrong. Aborting run.")
                            client.exit_tibia()
                            return
                        
                        print("Failed 11 times in a row. Waiting and retrying...")
                        fail_counter = 0
                        
                        client.close_market()
                        time.sleep(10)
                        client.wiggle()
                        afk_time = time.time()
                        client.open_market()
                        
                        i -= 11
                    continue
                
                fail_counter = 0
                retry_counter = 0
                f.write(str(values) + "\n")

                with open(os.path.join(results_location, "histories", f"{values.name.lower()}.csv"), "a+") as h:
                    h.write(values.history_string() + "\n")
        
    client.exit_tibia()

    os.replace(os.path.join(results_location, "fullscan_tmp.csv"), os.path.join(results_location, "fullscan.csv"))
    push_to_github(results_location)

    turn_off_display()

def push_to_github(results_repo_location: str):
    """
    Pushes the new market data from the results repo to GitHub.
    """
    try:
        repo = Repo(os.path.join(results_repo_location, ".git"))
        repo.git.add(all=True)
        repo.index.commit("Update market data")
        origin = repo.remote("origin")
        origin.push()
    except Exception as e:
        print(f"Error while pushing to git: {e}")

def turn_off_display():
    """Turns off the display by using xset.
    The display will turn on again when there is mouse or keyboard activity.
    This is done to save power.
    """
    os.system("xset dpms force off")

if __name__ == "__main__":
    with open("config.json", "r") as c:
        config = json.loads(c.read())

    turn_off_display()
    
    #schedule.every().day.at("10:15:00").do(lambda: observe_items(config["email"], config["password"], config["tibiaLocation"], config["resultsLocation"]))
    #observe_items(config["email"], config["password"], config["tibiaLocation"], config["resultsLocation"])
    do_market_search(config["email"], config["password"], config["tibiaLocation"], config["resultsLocation"])

    schedule.every().day.at("18:00:00").do(lambda: do_market_search(config["email"], config["password"], config["tibiaLocation"], config["resultsLocation"]))
    schedule.every().day.at("06:00:00").do(lambda: do_market_search(config["email"], config["password"], config["tibiaLocation"], config["resultsLocation"]))
    
    while True:
        schedule.run_pending()
        time.sleep(60)
