import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Estados de la conversación
RIESGO, STOP_LOSS, RATIO, PREGUNTA_PATRON, PATRON, TIMEFRAME = range(6)
CONFIG_CAPITAL, CONFIG_APALANCAMIENTO = 100, 101

# Token desde variable de entorno (SEGURIDAD) - NO hardcodear en producción
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN no configurado en variables de entorno")

# Configurar logging para producción
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Base de datos simple en memoria (en producción usarías una BD real)
user_capital_db = {}
user_leverage_db = {}

class RiskCalculator:
    def __init__(self):
        # Duración estimada por timeframe
        self.duraciones = {
            'M1': {'tiempo': '5-15 min', 'tipo': 'Scalping Ultra'},
            'M5': {'tiempo': '15-45 min', 'tipo': 'Scalping'},
            'M15': {'tiempo': '1-3 horas', 'tipo': 'Scalping/Intraday'},
            'M30': {'tiempo': '2-6 horas', 'tipo': 'Intraday'},
            'H1': {'tiempo': '4-12 horas', 'tipo': 'Intraday'},
            'H4': {'tiempo': '1-3 días', 'tipo': 'Swing Trading'},
            'D1': {'tiempo': '3-14 días', 'tipo': 'Swing Trading'},
            'W1': {'tiempo': '2-8 semanas', 'tipo': 'Position Trading'}
        }
    
    def get_duracion_operacion(self, timeframe):
        """Obtiene la duración estimada según el timeframe"""
        return self.duraciones.get(timeframe, {'tiempo': 'Variable', 'tipo': 'Personalizado'})
    
    def calculate_nocional(self, capital, riesgo_percent, stop_loss_percent, ratio, apalancamiento):
        """Calcula el VALOR NOCIONAL que debes poner en tu operación"""
        try:
            # Dinero que estás dispuesto a perder
            riesgo_usd = capital * (riesgo_percent / 100)
            
            # VALOR NOCIONAL = Riesgo ÷ Stop Loss %
            valor_nocional = riesgo_usd / (stop_loss_percent / 100)
            
            # Margen requerido por el exchange
            margen_requerido = valor_nocional / apalancamiento
            
            # Verificar que tenemos suficiente capital para el margen
            if margen_requerido > capital:
                # Reducir el valor nocional para que quepa
                margen_requerido = capital * 0.8  # Máximo 80% del capital
                valor_nocional = margen_requerido * apalancamiento
                riesgo_real = valor_nocional * (stop_loss_percent / 100)
            else:
                riesgo_real = riesgo_usd
            
            # Take Profit
            tp_percent = stop_loss_percent * ratio
            tp_usd = riesgo_real * ratio
            
            return {
                'capital': capital,
                'riesgo_percent': riesgo_percent,
                'riesgo_usd': riesgo_real,
                'stop_loss_percent': stop_loss_percent,
                'ratio': ratio,
                'apalancamiento': apalancamiento,
                'valor_nocional': valor_nocional,
                'margen_requerido': margen_requerido,
                'tp_usd': tp_usd,
                'tp_percent': tp_percent,
                'valido': True
            }
            
        except Exception as e:
            logger.error(f"Error en cálculo: {e}")
            return {'valido': False, 'error': str(e)}

calculator = RiskCalculator()

def get_user_capital(user_id):
    """Obtiene el capital configurado del usuario"""
    return user_capital_db.get(user_id)

def set_user_capital(user_id, capital):
    """Guarda el capital del usuario"""
    user_capital_db[user_id] = capital

def get_user_leverage(user_id):
    """Obtiene el apalancamiento configurado del usuario"""
    return user_leverage_db.get(user_id)

def set_user_leverage(user_id, leverage):
    """Guarda el apalancamiento del usuario"""
    user_leverage_db[user_id] = leverage

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    capital_guardado = get_user_capital(user_id)
    leverage_guardado = get_user_leverage(user_id)
    
    if capital_guardado and leverage_guardado:
        keyboard = [
            [KeyboardButton("📊 Calcular Operación")],
            [KeyboardButton("⚙️ Cambiar Capital"), KeyboardButton("⚡ Cambiar Apalancamiento")],
            [KeyboardButton("ℹ️ Ayuda")]
        ]
        mensaje = f"""
🤖 **BOT CALCULADORA DE ENTRADA**
📈 Cross Margin Trading

✅ **Capital:** ${capital_guardado:.2f}
✅ **Apalancamiento:** {leverage_guardado}x
✅ **Listo para calcular**

**Proceso súper rápido (3 pasos):**
Solo necesitas: Riesgo, SL, Ratio

¡Empezamos! 🚀
        """
    else:
        keyboard = [
            [KeyboardButton("⚙️ Configurar Capital")],
            [KeyboardButton("ℹ️ Ayuda")]
        ]
        mensaje = """
🤖 **BOT CALCULADORA DE ENTRADA**
📈 Cross Margin Trading

⚠️ **Configuración inicial requerida:**
• Capital total
• Apalancamiento preferido

Una vez configurado, solo 3 pasos por operación:
• Riesgo, SL, Ratio

¡Configura y acelera tus cálculos! 🚀
        """
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(mensaje, reply_markup=reply_markup, parse_mode='Markdown')

async def configurar_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚙️ **CONFIGURACIÓN INICIAL - PASO 1/2**\n\nIngresa tu capital total disponible:\n\n*Ejemplo: 100*",
        parse_mode='Markdown'
    )
    return CONFIG_CAPITAL

async def configurar_apalancamiento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    leverage_actual = get_user_leverage(user_id)
    
    if leverage_actual:
        await update.message.reply_text(
            f"⚡ **CONFIGURACIÓN DE APALANCAMIENTO**\n\nApalancamiento actual: {leverage_actual}x\n\nIngresa tu nuevo apalancamiento:\n\n*Ejemplo: 125 (para 125x)*",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "⚡ **CONFIGURACIÓN INICIAL - PASO 2/2**\n\nIngresa tu apalancamiento preferido:\n\n*Ejemplo: 125 (para 125x)*",
            parse_mode='Markdown'
        )
    return CONFIG_APALANCAMIENTO

async def save_capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        capital = float(update.message.text)
        if capital <= 0:
            await update.message.reply_text("❌ El capital debe ser mayor a 0")
            return CONFIG_CAPITAL
        
        user_id = update.effective_user.id
        set_user_capital(user_id, capital)
        
        # Para usuarios nuevos, preguntar apalancamiento automáticamente
        if user_id not in user_leverage_db:
            await update.message.reply_text(
                f"✅ **Capital guardado:** ${capital:.2f}\n\n⚡ **PASO 2/2**\n\n¿Qué apalancamiento prefieres usar normalmente?\n\n*Ejemplo: 125 (para 125x)*",
                parse_mode='Markdown'
            )
            return CONFIG_APALANCAMIENTO
        
        # Usuario existente solo cambiando capital
        leverage = get_user_leverage(user_id)
        keyboard = [
            [KeyboardButton("📊 Calcular Operación")],
            [KeyboardButton("⚙️ Cambiar Capital"), KeyboardButton("⚡ Cambiar Apalancamiento")],
            [KeyboardButton("ℹ️ Ayuda")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"✅ **Capital actualizado:** ${capital:.2f}\n✅ **Apalancamiento:** {leverage}x\n\n🚀 **¡Listo para operar!** 🎯",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Ingresa un número válido")
        return CONFIG_CAPITAL

async def save_leverage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        leverage = float(update.message.text)
        if leverage < 1 or leverage > 200:
            await update.message.reply_text("❌ El apalancamiento debe estar entre 1x y 200x")
            return CONFIG_APALANCAMIENTO
        
        user_id = update.effective_user.id
        set_user_leverage(user_id, leverage)
        capital = get_user_capital(user_id)
        
        keyboard = [
            [KeyboardButton("📊 Calcular Operación")],
            [KeyboardButton("⚙️ Cambiar Capital"), KeyboardButton("⚡ Cambiar Apalancamiento")],
            [KeyboardButton("ℹ️ Ayuda")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"✅ **CONFIGURACIÓN COMPLETA:**\n• Capital: ${capital:.2f}\n• Apalancamiento: {leverage}x\n\n🚀 **¡Listo para operar!**\nSolo 3 pasos por operación! 🎯",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Ingresa un número válido")
        return CONFIG_APALANCAMIENTO

async def nueva_operacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    capital = get_user_capital(user_id)
    leverage = get_user_leverage(user_id)
    
    if not capital or not leverage:
        await update.message.reply_text("❌ Primero debes configurar tu capital y apalancamiento. Usa ⚙️ Configurar Capital")
        return ConversationHandler.END
    
    # Limpiar datos anteriores y guardar valores persistentes
    context.user_data.clear()
    context.user_data['capital'] = capital
    context.user_data['apalancamiento'] = leverage
    
    keyboard = [[KeyboardButton("🔄 Reiniciar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"💰 **Capital:** ${capital:.2f}\n⚡ **Apalancamiento:** {leverage}x\n\n🎯 **PASO 1/3**\n\n¿Qué % de tu capital quieres arriesgar?\n\n*Ejemplo: 5 (= 5% = ${capital * 0.05:.2f})*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return RIESGO

async def get_riesgo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verificar si quiere reiniciar
    if update.message.text == "🔄 Reiniciar":
        return await nueva_operacion(update, context)
    
    try:
        riesgo = float(update.message.text)
        if riesgo <= 0 or riesgo > 50:
            keyboard = [[KeyboardButton("🔄 Reiniciar")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("❌ El riesgo debe estar entre 0.1% y 50%", reply_markup=reply_markup)
            return RIESGO
        
        context.user_data['riesgo'] = riesgo
        riesgo_usd = context.user_data['capital'] * (riesgo / 100)
        
        keyboard = [[KeyboardButton("🔄 Reiniciar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"✅ Riesgo: {riesgo}% = ${riesgo_usd:.2f}\n\n⛔ **PASO 2/3**\n\n¿Cuál será tu Stop Loss en %?\n\n*Ejemplo: 0.5 (= 0.5%)*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return STOP_LOSS
    except ValueError:
        keyboard = [[KeyboardButton("🔄 Reiniciar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("❌ Ingresa un número válido", reply_markup=reply_markup)
        return RIESGO

async def get_stop_loss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verificar si quiere reiniciar
    if update.message.text == "🔄 Reiniciar":
        return await nueva_operacion(update, context)
    
    try:
        stop_loss = float(update.message.text)
        if stop_loss <= 0 or stop_loss > 20:
            keyboard = [[KeyboardButton("🔄 Reiniciar")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("❌ El Stop Loss debe estar entre 0.1% y 20%", reply_markup=reply_markup)
            return STOP_LOSS
        
        context.user_data['stop_loss'] = stop_loss
        
        # Mostrar preview del valor nocional
        riesgo_usd = context.user_data['capital'] * (context.user_data['riesgo'] / 100)
        valor_nocional_preview = riesgo_usd / (stop_loss / 100)
        
        keyboard = [[KeyboardButton("🔄 Reiniciar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"✅ Stop Loss: {stop_loss}%\n\n💡 **Preview entrada:** ~${valor_nocional_preview:.2f}\n\n🔁 **PASO 3/3 (FINAL)**\n\n¿Cuál es tu ratio Risk:Reward?\n\n*Ejemplo: 1.24 (para 1:1.24)*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return RATIO
    except ValueError:
        keyboard = [[KeyboardButton("🔄 Reiniciar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("❌ Ingresa un número válido", reply_markup=reply_markup)
        return STOP_LOSS

async def get_ratio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verificar si quiere reiniciar
    if update.message.text == "🔄 Reiniciar":
        return await nueva_operacion(update, context)
    
    try:
        ratio = float(update.message.text)
        if ratio <= 0 or ratio > 10:
            keyboard = [[KeyboardButton("🔄 Reiniciar")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("❌ El ratio debe estar entre 0.1 y 10", reply_markup=reply_markup)
            return RATIO
        
        context.user_data['ratio'] = ratio
        
        # Calcular y mostrar preview final
        data = context.user_data
        riesgo_usd = data['capital'] * (data['riesgo'] / 100)
        valor_nocional = riesgo_usd / (data['stop_loss'] / 100)
        margen_preview = valor_nocional / data['apalancamiento']
        
        await update.message.reply_text(
            f"✅ Ratio: 1:{ratio}\n\n🎯 **CALCULANDO...**\n💡 Preview margen: ~${margen_preview:.2f}\n\n❓ ¿Estás operando algún patrón técnico específico?",
            parse_mode='Markdown'
        )
        
        keyboard = [
            [KeyboardButton("✅ SÍ"), KeyboardButton("❌ NO")],
            [KeyboardButton("🔄 Reiniciar")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text("Selecciona:", reply_markup=reply_markup)
        
        return PREGUNTA_PATRON
    except ValueError:
        keyboard = [[KeyboardButton("🔄 Reiniciar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("❌ Ingresa un número válido", reply_markup=reply_markup)
        return RATIO

async def get_pregunta_patron(update: Update, context: ContextTypes.DEFAULT_TYPE):
    respuesta = update.message.text
    
    # Verificar si quiere reiniciar
    if respuesta == "🔄 Reiniciar":
        return await nueva_operacion(update, context)
    
    if respuesta == "✅ SÍ":
        keyboard = [
            [KeyboardButton("Caja"), KeyboardButton("Interruptor")],
            [KeyboardButton("Angelito Extendido"), KeyboardButton("Malvado Extendido")],
            [KeyboardButton("Colorido"), KeyboardButton("Balancín")],
            [KeyboardButton("Muralla"), KeyboardButton("Liana")],
            [KeyboardButton("🔄 Reiniciar")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            "📊 **¿Qué patrón estás operando?**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return PATRON
        
    elif respuesta == "❌ NO":
        context.user_data['patron'] = None
        context.user_data['timeframe'] = None
        return await mostrar_resultado_final(update, context)
    
    else:
        keyboard = [
            [KeyboardButton("✅ SÍ"), KeyboardButton("❌ NO")],
            [KeyboardButton("🔄 Reiniciar")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("❌ Por favor selecciona SÍ o NO", reply_markup=reply_markup)
        return PREGUNTA_PATRON

async def get_patron(update: Update, context: ContextTypes.DEFAULT_TYPE):
    patron = update.message.text
    
    # Verificar si quiere reiniciar
    if patron == "🔄 Reiniciar":
        return await nueva_operacion(update, context)
    
    context.user_data['patron'] = patron
    
    keyboard = [
        [KeyboardButton("M1"), KeyboardButton("M5"), KeyboardButton("M15")],
        [KeyboardButton("M30"), KeyboardButton("H1"), KeyboardButton("H4")],
        [KeyboardButton("D1"), KeyboardButton("W1")],
        [KeyboardButton("🔄 Reiniciar")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"✅ Patrón: {patron}\n\n⏰ **Timeframe de análisis:**",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    return TIMEFRAME

async def get_timeframe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    timeframe = update.message.text
    
    # Verificar si quiere reiniciar
    if timeframe == "🔄 Reiniciar":
        return await nueva_operacion(update, context)
    
    context.user_data['timeframe'] = timeframe
    
    return await mostrar_resultado_final(update, context)

async def mostrar_resultado_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # CALCULAR EL VALOR NOCIONAL
    data = context.user_data
    result = calculator.calculate_nocional(
        data['capital'],
        data['riesgo'],
        data['stop_loss'],
        data['ratio'],
        data['apalancamiento']
    )
    
    if not result.get('valido', False):
        await update.message.reply_text(f"❌ Error: {result.get('error', 'Error desconocido')}")
        return ConversationHandler.END
    
    # RESULTADO FINAL - CON O SIN PATRÓN
    resultado_base = f"""**☃️ CAPITAL {result['capital']:.0f}$:**
├─ 🚧 Riesgo Día: {result['riesgo_percent']:.0f}%
├─ ⛔ Stop Loss: {result['stop_loss_percent']:.2f}%
├─ 🔁 Ratio: 1:{result['ratio']:.2f} ({result['tp_percent']:.2f}%)
└─ ⚡ X: {result['apalancamiento']:.0f}

╔════════════════════╗
║ 🧮  **ENTRADA:** **{result['valor_nocional']:.2f} USD** 
║ 🛎️ Margen: {result['margen_requerido']:.2f} USD   
╚════════════════════╝

📛TP: {result['tp_usd']:.2f} USD"""
    
    # Agregar patrón y timeframe solo si existen
    if data.get('patron') and data.get('timeframe'):
        # Obtener duración estimada
        duracion_info = calculator.get_duracion_operacion(data['timeframe'])
        
        resultado_base += f"""
🅿️**PATRÓN:** **{data['patron'].upper()}**
├─⏰ TF: {data['timeframe']}
└─💊 Formación: {duracion_info['tiempo']} ({duracion_info['tipo']})"""
    
    # Instrucciones finales
    resultado_base += f"""

📋 **instrucciones:**
• Aprende a pescar con método y disciplina🎣
• Configura sl en {result['stop_loss_percent']:.2f}%
• tp automático en {result['tp_percent']:.2f}%
    """
    
    keyboard = [
        [KeyboardButton("📊 Calcular Operación")],
        [KeyboardButton("⚙️ Cambiar Capital"), KeyboardButton("⚡ Cambiar Apalancamiento")],
        [KeyboardButton("ℹ️ Ayuda")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(resultado_base, reply_markup=reply_markup, parse_mode='Markdown')
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('❌ Operación cancelada.')
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 **GUÍA DE USO SÚPER RÁPIDA**

**🔧 Configuración inicial (una sola vez):**
1. Capital total
2. Apalancamiento preferido

**⚡ Cálculo express (solo 3 pasos):**
1. Riesgo %
2. Stop Loss %
3. Ratio R:R

**🎯 Comandos:**
• **/start** - Menú principal
• **/capital** - Cambiar capital
• **/leverage** - Cambiar apalancamiento
• **/ayuda** - Esta guía

**💡 Beneficio:** De 8 pasos a solo 3 pasos ⚡
**🚀 Velocidad:** Configuración persistente
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def capital_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    capital_actual = get_user_capital(user_id)
    
    if capital_actual:
        await update.message.reply_text(
            f"⚙️ **Capital actual:** ${capital_actual:.2f}\n\nIngresa tu nuevo capital:",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("⚙️ Ingresa tu capital:")
    
    return CONFIG_CAPITAL

async def leverage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    leverage_actual = get_user_leverage(user_id)
    
    if leverage_actual:
        await update.message.reply_text(
            f"⚡ **Apalancamiento actual:** {leverage_actual}x\n\nIngresa tu nuevo apalancamiento:\n\n*Ejemplo: 125 (para 125x)*",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "⚡ **CONFIGURACIÓN DE APALANCAMIENTO**\n\nIngresa tu apalancamiento preferido:\n\n*Ejemplo: 125 (para 125x)*",
            parse_mode='Markdown'
        )
    return CONFIG_APALANCAMIENTO

# Función para manejo de errores
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)

def main():
    """Función principal mejorada para producción"""
    print("🤖 Bot Express Trading iniciado en modo PRODUCCIÓN...")
    print("✅ Configuración persistente habilitada")
    print("✅ Logging mejorado para producción")
    print("✅ Manejo de errores robusto")
    
    try:
        # Verificar token
        if not TOKEN:
            raise ValueError("TOKEN de Telegram no configurado")
        
        application = Application.builder().token(TOKEN).build()
        
        # Handler de errores
        application.add_error_handler(error_handler)
        
        # ConversationHandler para configurar capital
        config_capital_handler = ConversationHandler(
            entry_points=[
                CommandHandler('capital', capital_command),
                MessageHandler(filters.Regex('^⚙️ Configurar Capital), configurar_capital),
                MessageHandler(filters.Regex('^⚙️ Cambiar Capital), capital_command)
            ],
            states={
                CONFIG_CAPITAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_capital)],
                CONFIG_APALANCAMIENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_leverage)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        # ConversationHandler para configurar solo apalancamiento
        config_leverage_handler = ConversationHandler(
            entry_points=[
                CommandHandler('leverage', leverage_command),
                MessageHandler(filters.Regex('^⚡ Cambiar Apalancamiento), leverage_command)
            ],
            states={
                CONFIG_APALANCAMIENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_leverage)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        # ConversationHandler para calcular operaciones
        calc_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex('^📊 Calcular Operación), nueva_operacion)
            ],
            states={
                RIESGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_riesgo)],
                STOP_LOSS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stop_loss)],
                RATIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ratio)],
                PREGUNTA_PATRON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pregunta_patron)],
                PATRON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_patron)],
                TIMEFRAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_timeframe)],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )
        
        # Agregar handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("ayuda", help_command))
        application.add_handler(MessageHandler(filters.Regex('^ℹ️ Ayuda), help_command))
        application.add_handler(config_capital_handler)
        application.add_handler(config_leverage_handler)
        application.add_handler(calc_handler)
        
        print("🚀 Bot iniciado correctamente...")
        print("📡 Esperando mensajes...")
        
        # Para producción: usar polling robusto
        application.run_polling(
            poll_interval=1.0,
            timeout=10,
            bootstrap_retries=3,
            read_timeout=6,
            write_timeout=6,
            connection_pool_size=8
        )
        
    except Exception as e:
        logger.error(f"❌ Error crítico: {e}")
        print(f"❌ Error crítico: {e}")

if __name__ == '__main__':
    main()
