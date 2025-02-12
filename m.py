import os
from telethon import TelegramClient, events, Button
from thefuzz import process  # For fuzzy search
import firebase_admin
from firebase_admin import credentials, db

# Initialize Firebase
cred = credentials.Certificate("ad.json")  # Replace with your Firebase private key path
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://pcgames-ab951-default-rtdb.firebaseio.com/'  # Replace with your Firebase database URL
})

# Reference to the Firebase database
games_ref = db.reference('games')
game_details_ref = db.reference('game_details')

# Replace these with your own values
API_ID = 3231807  # Get from https://my.telegram.org
API_HASH = '4f96bd76bf9f5bdeac602e7fddbb9f10'  # Get from https://my.telegram.org
BOT_TOKEN = '7291239490:AAE1nl8FfEcEwgpC9jTQtLj2y4rXy882UUM'  # Get from @BotFather

# Initialize the Telegram client
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Pagination variables
GAMES_PER_PAGE = 10
current_page = {}

# Command: /start
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    welcome_message = (
        "👋 Welcome to the Game Bot!\n\n"
        "Here's how you can use me:\n"
        "1. Use /games to see the list of available games.\n"
        "2. Use /search <game_name> to search for a game.\n"
        "3. Use /pay <payment_id> <game_id> to process a payment.\n\n"
        "Enjoy!"
    )
    await event.respond(welcome_message)

# Command: /game
@bot.on(events.NewMessage(pattern='/game'))
async def show_games(event):
    user_id = event.sender_id
    current_page[user_id] = 0  # Reset to the first page
    await send_games_page(event, user_id)

# Function to send or edit a page of games
async def send_games_page(event, user_id, page=0):
    games = games_ref.get()  # Fetch games from Firebase
    if not games:
        await event.respond("No games found in the database.")
        return

    start_index = page * GAMES_PER_PAGE
    end_index = start_index + GAMES_PER_PAGE
    games_page = games[start_index:end_index]

    buttons = []
    for game in games_page:
        buttons.append([Button.inline(game['name'], data=game['id'])])

    # Add pagination buttons
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(Button.inline("⬅️ Previous", data=f"prev_{page}"))
    if end_index < len(games):
        pagination_buttons.append(Button.inline("Next ➡️", data=f"next_{page}"))
    if pagination_buttons:
        buttons.append(pagination_buttons)

    # Edit the existing message or send a new one
    if hasattr(event, 'edit'):  # If it's a callback query, try to edit the message
        try:
            await event.edit(f"Page {page + 1} of {len(games) // GAMES_PER_PAGE + 1}", buttons=buttons)
        except Exception as e:
            # If editing fails, send a new message
            await event.respond(f"Page {page + 1} of {len(games) // GAMES_PER_PAGE + 1}", buttons=buttons)
    else:  # If it's a new command, send a new message
        await event.respond(f"Page {page + 1} of {len(games) // GAMES_PER_PAGE + 1}", buttons=buttons)

# Callback query handler for game selection and pagination
@bot.on(events.CallbackQuery)
async def handle_callback(event):
    user_id = event.sender_id
    data = event.data.decode('utf-8')

    if data.startswith("prev_") or data.startswith("next_"):
        # Handle pagination
        page = int(data.split("_")[1])
        if data.startswith("prev_"):
            page -= 1
        elif data.startswith("next_"):
            page += 1
        current_page[user_id] = page
        await send_games_page(event, user_id, page)
    else:
        # Handle game selection
        game_id = data
        game_details = game_details_ref.get()  # Fetch game details from Firebase
        detail = next((item for item in game_details if item['id'] == game_id), None)
        if detail:
            # Send game details
            await event.respond(f"Game: {detail['name']}\nGameID: {detail['id']}\nDescription: {detail['description']}\nPrice: {detail['price']}")

            # Send the post from the channel if post_no is available
            if 'post_no' in detail:
                try:
                    # Fetch the post from the channel
                    channel_username = 'pcgamehubb'  # Replace with your channel username
                    post = await bot.get_messages(channel_username, ids=detail['post_no'])
                    if post:
                        await event.respond("Here's the post for this game:")
                        await event.respond(post)
                    else:
                        await event.respond("Post not found in the channel.")
                except Exception as e:
                    await event.respond(f"Failed to fetch the post: {str(e)}")
            else:
                await event.respond("No post available for this game.")
        else:
            await event.respond("Game details not found!")

# Command: /search
@bot.on(events.NewMessage(pattern='/search'))
async def search_games(event):
    try:
        search_query = event.raw_text.split(maxsplit=1)[1].lower()  # Get the search query

        # Fetch games from Firebase
        games = games_ref.get()
        if not games:
            await event.respond("No games found in the database.")
            return

        # Perform fuzzy search
        matched_games = process.extract(
            search_query,
            [game['name'] for game in games],
            limit=10  # Limit to 10 results
        )

        if matched_games:
            buttons = []
            for game_name, score in matched_games:
                if score >= 50:  # Only include matches with a similarity score >= 50
                    game = next((g for g in games if g['name'] == game_name), None)
                    if game:
                        buttons.append([Button.inline(game['name'], data=game['id'])])

            if buttons:
                await event.respond(f"Search results for '{search_query}':", buttons=buttons)
            else:
                await event.respond(f"No similar games found for '{search_query}'.")
        else:
            await event.respond(f"No games found for '{search_query}'.")
    except IndexError:
        await event.respond("Please provide a search term. Usage: /search <game_name>")

# Command: /pay
@bot.on(events.NewMessage(pattern='/pay'))
async def process_payment(event):
    try:
        # Extract payment ID and game ID from the command
        args = event.raw_text.split()
        if len(args) < 3:
            await event.respond("Please provide both payment ID and game ID. Usage: /pay <payment_id> <game_id>")
            return

        payment_id = args[1]
        game_id = args[2]

        # Fetch game details from Firebase
        game_details = game_details_ref.get()
        game = next((g for g in game_details if g['id'] == game_id), None)
        if not game:
            await event.respond(f"Game ID {game_id} not found.")
            return

        # Respond to the user
        await event.respond(
            f"Payment ID {payment_id} received for game '{game['name']}'. Processing payment..."
        )

        # Send the payment ID and game details to the admin
        admin_user_id = 1721370371  # Replace with the admin's user ID
        await bot.send_message(
            admin_user_id,
            f"New payment received!\n"
            f"Payment ID: {payment_id}\n"
            f"Game: {game['name']}\n"
            f"Price: {game['price']}\n"
            f"From user: {event.sender_id}"
        )
        admin_user_id2 = 5879404457  # Replace with the admin's user ID
        await bot.send_message(
            admin_user_id2,
            f"New payment received!\n"
            f"Payment ID: {payment_id}\n"
            f"Game: {game['name']}\n"
            f"Price: {game['price']}\n"
            f"From user: {event.sender_id}"
        )
    except Exception as e:
        await event.respond(f"An error occurred: {str(e)}")



#<==========================================Admin Section ==============================>
ADMIN_USER_ID = 5879404457
# Command: /start
@bot.on(events.NewMessage(pattern='/starta'))
async def start(event):
    if event.sender_id != ADMIN_USER_ID:
        await event.respond("You are not authorized to use this bot.")
        return

    welcome_message = (
        "👋 Welcome to the Admin Bot!\n\n"
        "Here's how you can use me:\n"
        "1. Use /addgame to add a new game.\n"
        "2. Use /addgamedetails to add details for a game.\n"
        "3. Use /listgames to see all game IDs.\n"
        "4. Use /deletegame to delete a game and its details.\n\n"
        "Enjoy!"
    )
    await event.respond(welcome_message)

# Command: /addgame
@bot.on(events.NewMessage(pattern='/addgame'))
async def add_game(event):
    if event.sender_id != ADMIN_USER_ID:
        await event.respond("You are not authorized to use this bot.")
        return

    try:
        # Extract game ID and name from the command
        args = event.raw_text.split(";")
        if len(args) < 3:
            await event.respond("Usage: /addgame ;<game_id> ;<game_name>")
            return

        game_id = args[1]
        game_name = args[2]

        # Check if the game ID already exists
        if games_ref.child(game_id).get():
            await event.respond(f"Game ID '{game_id}' already exists!")
            return

        # Add the game to Firebase
        games_ref.child(game_id).set({
            'id': game_id,
            'name': game_name
        })

        await event.respond(f"Game '{game_name}' with ID '{game_id}' added successfully!")
    except Exception as e:
        await event.respond(f"An error occurred: {str(e)}")

# Command: /addgamedetails
@bot.on(events.NewMessage(pattern='/addgamedetails'))
async def add_game_details(event):
    if event.sender_id != ADMIN_USER_ID:
        await event.respond("You are not authorized to use this bot.")
        return

    try:
        # Extract game details from the command
        args = event.raw_text.split(";")
        if len(args) < 6:
            await event.respond("Usage: /addgamedetails ;<game_id> ;<name> ;<description> ;<price> ;<post_no>")
            return

        game_id = args[1]
        name = args[2]
        description = args[3]
        price = args[4]
        post_no = int(args[5])

        # Check if the game ID exists in the games collection
        if not games_ref.child(game_id).get():
            await event.respond(f"Game ID '{game_id}' does not exist in the games collection!")
            return

        # Add the game details to Firebase
        game_details_ref.child(game_id).set({
            'id': game_id,
            'name': name,
            'description': description,
            'price': price,
            'post_no': post_no
        })

        await event.respond(f"Details for game '{name}' with ID '{game_id}' added successfully!")
    except Exception as e:
        await event.respond(f"An error occurred: {str(e)}")

# Command: /listgames
@bot.on(events.NewMessage(pattern='/listgames'))
async def list_games(event):
    if event.sender_id != ADMIN_USER_ID:
        await event.respond("You are not authorized to use this bot.")
        return

    try:
        # Fetch all games from Firebase
        games = games_ref.get()
        if not games:
            await event.respond("No games found in the database.")
            return

        # List all game IDs
        game_ids = "\n".join([game['id'] for game in games])
        await event.respond(f"Game IDs in the database:\n{game_ids}")
    except Exception as e:
        await event.respond(f"An error occurred: {str(e)}")

# Command: /listgames
@bot.on(events.NewMessage(pattern='/listgames'))
async def list_games(event):
    if event.sender_id != ADMIN_USER_ID:
        await event.respond("You are not authorized to use this bot.")
        return

    try:
        # Fetch all games from Firebase
        games = games_ref.get()
        if not games:
            await event.respond("No games found in the database.")
            return

        # List all game IDs and names
        game_list = "\n".join([f"ID: {game['id']}, Name: {game['name']}" for game in games])
        await event.respond(f"Games in the database:\n{game_list}")
    except Exception as e:
        await event.respond(f"An error occurred: {str(e)}")


# Command: /deletegame
@bot.on(events.NewMessage(pattern='/deletegame'))
async def delete_game(event):
    if event.sender_id != ADMIN_USER_ID:
        await event.respond("You are not authorized to use this bot.")
        return

    try:
        # Extract game ID from the command
        args = event.raw_text.split(maxsplit=1)
        if len(args) < 2:
            await event.respond("Usage: /deletegame <game_id>")
            return

        game_id = args[1]

        # Check if the game ID exists
        if not games_ref.child(game_id).get():
            await event.respond(f"Game ID '{game_id}' does not exist!")
            return

        # Delete the game and its details
        games_ref.child(game_id).delete()
        game_details_ref.child(game_id).delete()

        await event.respond(f"Game with ID '{game_id}' and its details deleted successfully!")
    except Exception as e:
        await event.respond(f"An error occurred: {str(e)}")

# Command: /send
@bot.on(events.NewMessage(pattern='/send'))
async def send_post(event):
    if event.sender_id != ADMIN_USER_ID:
        await event.respond("You are not authorized to use this bot.")
        return
    try:
        # Extract user ID and post number from the command
        args = event.raw_text.split(";")
        if len(args) < 3:
            await event.respond("Usage: /send ;<user_id>;<post_no>")
            return
        user_id = int(args[1])  # Convert user ID to integer
        post_no = int(args[2])  # Convert post number to integer
        # Fetch the post from the channel
        channel_username = -1002389618590  # Replace with your channel username
        post = await bot.get_messages(channel_username, ids=post_no)
        if not post:
            await event.respond(f"Post number {post_no} not found in the channel.")
            return
        # Forward the post to the user
        await bot.send_message(user_id, f"Here's the post you requested (Post No: {post_no}):")
        await bot.forward_messages(user_id, post)

        await event.respond(f"Post number {post_no} sent to user {user_id} successfully!")
    except ValueError:
        await event.respond("Invalid user ID or post number. Please provide numeric values.")
    except Exception as e:
        await event.respond(f"An error occurred: {str(e)}")

# Start the bot
print("Bot is running...")
bot.run_until_disconnected()
