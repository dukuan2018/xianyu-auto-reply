"""
闲鱼订单详情获取工具
基于Playwright实现订单详情页面访问和数据提取
"""

import asyncio
import time
import sys
import os
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger
import re
import json
from threading import Lock
from collections import defaultdict

# 修复Docker环境中的asyncio事件循环策略问题
if sys.platform.startswith('linux') or os.getenv('DOCKER_ENV'):
    try:
        # 在Linux/Docker环境中设置事件循环策略
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    except Exception as e:
        logger.warning(f"设置事件循环策略失败: {e}")

# 确保在Docker环境中使用正确的事件循环
if os.getenv('DOCKER_ENV'):
    try:
        # 强制使用SelectorEventLoop（在Docker中更稳定）
        if hasattr(asyncio, 'SelectorEventLoop'):
            loop = asyncio.SelectorEventLoop()
            asyncio.set_event_loop(loop)
    except Exception as e:
        logger.warning(f"设置SelectorEventLoop失败: {e}")


class OrderDetailFetcher:
    """闲鱼订单详情获取器"""

    # 类级别的锁字典，为每个order_id维护一个锁
    _order_locks = defaultdict(lambda: asyncio.Lock())

    def __init__(self, cookie_string: str = None, headless: bool = True):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.headless = headless  # 保存headless设置

        # 请求头配置
        self.headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8,ru;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1"
        }

        # Cookie配置 - 支持动态传入
        self.cookie = cookie_string

    async def init_browser(self, headless: bool = None):
        """初始化浏览器"""
        try:
            # 如果没有传入headless参数，使用实例的设置
            if headless is None:
                headless = self.headless

            logger.info(f"开始初始化浏览器，headless模式: {headless}")

            self.playwright = await async_playwright().start()

            # 启动浏览器（Docker环境优化）
            browser_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--disable-features=TranslateUI',
                '--disable-ipc-flooding-protection',
                '--disable-extensions',
                '--disable-default-apps',
                '--disable-sync',
                '--disable-translate',
                '--hide-scrollbars',
                '--mute-audio',
                '--no-default-browser-check',
                '--no-pings'
            ]

            # 移除--single-process参数，使用多进程模式提高稳定性
            # if os.getenv('DOCKER_ENV'):
            #     browser_args.append('--single-process')  # 注释掉，避免崩溃

            # 在Docker环境中添加额外参数
            if os.getenv('DOCKER_ENV'):
                browser_args.extend([
                    '--disable-background-networking',
                    '--disable-background-timer-throttling',
                    '--disable-client-side-phishing-detection',
                    '--disable-default-apps',
                    '--disable-hang-monitor',
                    '--disable-popup-blocking',
                    '--disable-prompt-on-repost',
                    '--disable-sync',
                    '--disable-web-resources',
                    '--metrics-recording-only',
                    '--no-first-run',
                    '--safebrowsing-disable-auto-update',
                    '--enable-automation',
                    '--password-store=basic',
                    '--use-mock-keychain',
                    # 添加内存优化和稳定性参数
                    '--memory-pressure-off',
                    '--max_old_space_size=512',
                    '--disable-ipc-flooding-protection',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-features=TranslateUI,BlinkGenPropertyTrees',
                    '--disable-logging',
                    '--disable-permissions-api',
                    '--disable-notifications',
                    '--no-pings',
                    '--no-zygote'
                ])

            logger.info(f"启动浏览器，参数: {browser_args}")
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                args=browser_args
            )

            logger.info("浏览器启动成功，创建上下文...")

            # 创建浏览器上下文
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
            )

            logger.info("浏览器上下文创建成功，设置HTTP头...")

            # 设置额外的HTTP头
            await self.context.set_extra_http_headers(self.headers)

            logger.info("创建页面...")

            # 创建页面
            self.page = await self.context.new_page()

            logger.info("页面创建成功，设置Cookie...")

            # 设置Cookie
            await self._set_cookies()

            # 等待一段时间确保浏览器完全初始化
            await asyncio.sleep(1)

            logger.info("浏览器初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            await self._force_close_browser()
            return False

    async def _set_cookies(self):
        """设置Cookie"""
        try:
            # 解析Cookie字符串
            cookies = []
            for cookie_pair in self.cookie.split('; '):
                if '=' in cookie_pair:
                    name, value = cookie_pair.split('=', 1)
                    cookies.append({
                        'name': name.strip(),
                        'value': value.strip(),
                        'domain': '.goofish.com',
                        'path': '/'
                    })
            
            # 添加Cookie到上下文
            await self.context.add_cookies(cookies)
            logger.info(f"已设置 {len(cookies)} 个Cookie")
            
        except Exception as e:
            logger.error(f"设置Cookie失败: {e}")

    async def fetch_order_detail(self, order_id: str, timeout: int = 30, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        获取订单详情（带锁机制和数据库缓存）

        Args:
            order_id: 订单ID
            timeout: 超时时间（秒）

        Returns:
            包含订单详情的字典，失败时返回None
        """
        # 获取该订单ID的锁
        order_lock = self._order_locks[order_id]

        async with order_lock:
            logger.info(f"🔒 获取订单 {order_id} 的锁，开始处理...")

            try:
                if use_cache:
                    # 首先查询数据库中是否已存在该订单（在初始化浏览器之前）
                    from db_manager import db_manager
                    existing_order = db_manager.get_order_by_id(order_id)

                    if existing_order:
                        cached_buyer_id = existing_order.get('buyer_id', '')
                        if cached_buyer_id:
                            logger.info(f"📋 订单 {order_id} 已存在于数据库中且有买家ID，直接返回缓存详情")
                            print(f"✅ 订单 {order_id} 使用缓存数据，跳过浏览器获取")

                            result = {
                                'order_id': existing_order['order_id'],
                                'buyer_id': cached_buyer_id,
                                'url': f"https://www.goofish.com/order-detail?orderId={order_id}&role=seller",
                                'title': f"订单详情 - {order_id}",
                                'sku_info': {
                                    'spec_name': existing_order.get('spec_name', ''),
                                    'spec_value': existing_order.get('spec_value', ''),
                                    'quantity': existing_order.get('quantity', '')
                                },
                                'spec_name': existing_order.get('spec_name', ''),
                                'spec_value': existing_order.get('spec_value', ''),
                                'quantity': existing_order.get('quantity', ''),
                                'timestamp': time.time(),
                                'from_cache': True
                            }
                            return result

                        logger.info(f"📋 订单 {order_id} 已存在但买家ID为空，继续访问详情页补充买家ID")

                if not await self._ensure_browser_ready():
                    logger.error("浏览器初始化失败，无法获取订单详情")
                    return None

                # 构建订单详情URL
                url = f"https://www.goofish.com/order-detail?orderId={order_id}&role=seller"
                logger.info(f"开始访问订单详情页面: {url}")

                # 访问页面（带重试机制）
                max_retries = 2
                response = None

                for retry in range(max_retries + 1):
                    try:
                        response = await self.page.goto(url, wait_until='networkidle', timeout=timeout * 1000)

                        if response and response.status == 200:
                            break
                        else:
                            logger.warning(f"页面访问失败，状态码: {response.status if response else 'None'}，重试 {retry + 1}/{max_retries + 1}")

                    except Exception as e:
                        logger.warning(f"页面访问异常: {e}，重试 {retry + 1}/{max_retries + 1}")

                        # 如果是浏览器连接问题，尝试重新初始化
                        if "Target page, context or browser has been closed" in str(e):
                            logger.info("检测到浏览器连接断开，尝试重新初始化...")
                            if await self._ensure_browser_ready():
                                logger.info("浏览器重新初始化成功，继续重试...")
                                continue
                            else:
                                logger.error("浏览器重新初始化失败")
                                return None

                        if retry == max_retries:
                            logger.error(f"页面访问最终失败: {e}")
                            return None

                        await asyncio.sleep(1)  # 重试前等待1秒

                if not response or response.status != 200:
                    logger.error(f"页面访问最终失败，状态码: {response.status if response else 'None'}")
                    return None

                logger.info("页面加载成功，等待内容渲染...")

                # 等待页面完全加载
                try:
                    await self.page.wait_for_load_state('networkidle')
                except Exception as e:
                    logger.warning(f"等待页面加载状态失败: {e}")
                    # 继续执行，不中断流程

                # 额外等待确保动态内容加载完成
                await asyncio.sleep(3)

                # 获取并解析SKU信息
                sku_info = await self._get_sku_content()

                # 获取页面标题
                try:
                    title = await self.page.title()
                except Exception as e:
                    logger.warning(f"获取页面标题失败: {e}")
                    title = f"订单详情 - {order_id}"

                buyer_id = await self._extract_buyer_id_from_page()

                result = {
                    'order_id': order_id,
                    'buyer_id': buyer_id,
                    'url': url,
                    'title': title,
                    'sku_info': sku_info,  # 包含解析后的规格信息
                    'spec_name': sku_info.get('spec_name', '') if sku_info else '',
                    'spec_value': sku_info.get('spec_value', '') if sku_info else '',
                    'quantity': sku_info.get('quantity', '') if sku_info else '',  # 数量
                    'timestamp': time.time(),
                    'from_cache': False  # 标记数据来源
                }

                logger.info(f"订单详情获取成功: {order_id}")
                if buyer_id:
                    logger.info(f"买家ID: {buyer_id}")
                if sku_info:
                    logger.info(f"规格信息 - 名称: {result['spec_name']}, 值: {result['spec_value']}")
                    logger.info(f"数量: {result['quantity']}")
                return result

            except Exception as e:
                logger.error(f"获取订单详情失败: {e}")
                return None

    def _parse_sku_content(self, sku_content: str) -> Dict[str, str]:
        """
        解析SKU内容，根据冒号分割规格名称和规格值

        Args:
            sku_content: 原始SKU内容字符串

        Returns:
            包含规格名称和规格值的字典，如果解析失败则返回空字典
        """
        try:
            if not sku_content or ':' not in sku_content:
                logger.warning(f"SKU内容格式无效或不包含冒号: {sku_content}")
                return {}

            # 根据冒号分割
            parts = sku_content.split(':', 1)  # 只分割第一个冒号

            if len(parts) == 2:
                spec_name = parts[0].strip()
                spec_value = parts[1].strip()

                if spec_name and spec_value:
                    result = {
                        'spec_name': spec_name,
                        'spec_value': spec_value
                    }
                    logger.info(f"SKU解析成功 - 规格名称: {spec_name}, 规格值: {spec_value}")
                    return result
                else:
                    logger.warning(f"SKU解析失败，规格名称或值为空: 名称='{spec_name}', 值='{spec_value}'")
                    return {}
            else:
                logger.warning(f"SKU内容分割失败: {sku_content}")
                return {}

        except Exception as e:
            logger.error(f"解析SKU内容异常: {e}")
            return {}

    async def _extract_buyer_id_from_page(self) -> str:
        """从订单详情页源码或可见文本中尽量提取买家ID。"""
        try:
            if not await self._check_browser_status():
                return ''

            sources = []
            try:
                sources.append(await self.page.content())
            except Exception as e:
                logger.debug(f"获取页面源码失败，跳过 buyer_id 源码解析: {e}")
            try:
                sources.append(await self.page.inner_text('body'))
            except Exception as e:
                logger.debug(f"获取页面文本失败，跳过 buyer_id 文本解析: {e}")

            patterns = [
                r'"(?:buyerId|buyer_id|buyerUserId|buyerUserID|peerUserId|peer_user_id)"\s*:\s*"([^"]+)"',
                r"'(?:buyerId|buyer_id|buyerUserId|buyerUserID|peerUserId|peer_user_id)'\s*:\s*'([^']+)'",
                r'(?:buyerId|buyer_id|buyerUserId|buyerUserID|peerUserId|peer_user_id)\s*[:=]\s*["\']?([A-Za-z0-9+/=_\-.]{6,})',
                r'(?:买家ID|买家id|买家用户ID|买家用户id)\s*[:：]\s*([A-Za-z0-9+/=_\-.]{6,})',
            ]

            for source in sources:
                if not source:
                    continue
                for pattern in patterns:
                    match = re.search(pattern, source, re.IGNORECASE | re.DOTALL)
                    if match:
                        buyer_id = match.group(1).strip()
                        if buyer_id:
                            logger.info(f"提取到买家ID: {buyer_id}")
                            print(f"👤 买家ID: {buyer_id}")
                            return buyer_id

            logger.warning("订单详情页未提取到买家ID")
            return ''
        except Exception as e:
            logger.warning(f"提取买家ID失败: {e}")
            return ''

    async def _get_sku_content(self) -> Optional[Dict[str, str]]:
        """获取并解析SKU内容，包括规格和数量"""
        try:
            # 检查浏览器状态
            if not await self._check_browser_status():
                logger.error("浏览器状态异常，无法获取SKU内容")
                return {}

            result = {}

            # 获取所有 sku--u_ddZval 元素
            sku_selector = '.sku--u_ddZval'
            sku_elements = await self.page.query_selector_all(sku_selector)

            logger.info(f"找到 {len(sku_elements)} 个 sku--u_ddZval 元素")
            print(f"🔍 找到 {len(sku_elements)} 个 sku--u_ddZval 元素")

            # 处理 sku--u_ddZval 元素
            if len(sku_elements) == 2:
                # 有两个元素：第一个是规格，第二个是数量
                logger.info("检测到两个 sku--u_ddZval 元素，第一个为规格，第二个为数量")
                print("📋 检测到两个元素：第一个为规格，第二个为数量")

                # 处理规格（第一个元素）
                spec_content = await sku_elements[0].text_content()
                if spec_content:
                    spec_content = spec_content.strip()
                    logger.info(f"规格原始内容: {spec_content}")
                    print(f"🛍️ 规格原始内容: {spec_content}")

                    # 解析规格内容
                    parsed_spec = self._parse_sku_content(spec_content)
                    if parsed_spec:
                        result.update(parsed_spec)
                        print(f"📋 规格名称: {parsed_spec['spec_name']}")
                        print(f"📝 规格值: {parsed_spec['spec_value']}")

                # 处理数量（第二个元素）
                quantity_content = await sku_elements[1].text_content()
                if quantity_content:
                    quantity_content = quantity_content.strip()
                    logger.info(f"数量原始内容: {quantity_content}")
                    print(f"📦 数量原始内容: {quantity_content}")

                    # 从数量内容中提取数量值（使用冒号分割，取后面的值）
                    if ':' in quantity_content:
                        quantity_value = quantity_content.split(':', 1)[1].strip()
                        # 去掉数量值前面的 'x' 符号（如 "x2" -> "2"）
                        if quantity_value.startswith('x'):
                            quantity_value = quantity_value[1:]
                        result['quantity'] = quantity_value
                        logger.info(f"提取到数量: {quantity_value}")
                        print(f"🔢 数量: {quantity_value}")
                    else:
                        # 去掉数量值前面的 'x' 符号（如 "x2" -> "2"）
                        if quantity_content.startswith('x'):
                            quantity_content = quantity_content[1:]
                        result['quantity'] = quantity_content
                        logger.info(f"数量内容无冒号，直接使用: {quantity_content}")
                        print(f"🔢 数量: {quantity_content}")

            elif len(sku_elements) == 1:
                # 只有一个元素：判断是否包含"数量"
                logger.info("检测到一个 sku--u_ddZval 元素，判断是规格还是数量")
                print("📋 检测到一个元素，判断是规格还是数量")

                content = await sku_elements[0].text_content()
                if content:
                    content = content.strip()
                    logger.info(f"元素原始内容: {content}")
                    print(f"🛍️ 元素原始内容: {content}")

                    if '数量' in content:
                        # 这是数量信息
                        logger.info("判断为数量信息")
                        print("📦 判断为数量信息")

                        if ':' in content:
                            quantity_value = content.split(':', 1)[1].strip()
                            # 去掉数量值前面的 'x' 符号（如 "x2" -> "2"）
                            if quantity_value.startswith('x'):
                                quantity_value = quantity_value[1:]
                            result['quantity'] = quantity_value
                            logger.info(f"提取到数量: {quantity_value}")
                            print(f"🔢 数量: {quantity_value}")
                        else:
                            # 去掉数量值前面的 'x' 符号（如 "x2" -> "2"）
                            if content.startswith('x'):
                                content = content[1:]
                            result['quantity'] = content
                            logger.info(f"数量内容无冒号，直接使用: {content}")
                            print(f"🔢 数量: {content}")
                    else:
                        # 这是规格信息
                        logger.info("判断为规格信息")
                        print("📋 判断为规格信息")

                        parsed_spec = self._parse_sku_content(content)
                        if parsed_spec:
                            result.update(parsed_spec)
                            print(f"📋 规格名称: {parsed_spec['spec_name']}")
                            print(f"📝 规格值: {parsed_spec['spec_value']}")
            else:
                logger.warning(f"未找到或找到异常数量的 sku--u_ddZval 元素: {len(sku_elements)}")
                print(f"⚠️ 未找到或找到异常数量的元素: {len(sku_elements)}")

                # 如果没有找到sku--u_ddZval元素，设置默认数量为1
                if len(sku_elements) == 0:
                    result['quantity'] = '1'
                    logger.info("未找到sku--u_ddZval元素，数量默认设置为1")
                    print("📦 数量默认设置为: 1")

                # 尝试获取页面的所有class包含sku的元素进行调试
                all_sku_elements = await self.page.query_selector_all('[class*="sku"]')
                if all_sku_elements:
                    logger.info(f"找到 {len(all_sku_elements)} 个包含'sku'的元素")
                    for i, element in enumerate(all_sku_elements):
                        class_name = await element.get_attribute('class')
                        text_content = await element.text_content()
                        logger.info(f"SKU元素 {i+1}: class='{class_name}', text='{text_content}'")

            # 确保数量字段存在，如果不存在则设置为1
            if 'quantity' not in result:
                result['quantity'] = '1'
                logger.info("未获取到数量信息，默认设置为1")
                print("📦 数量默认设置为: 1")

            # 打印最终结果
            if result:
                logger.info(f"最终解析结果: {result}")
                print("✅ 解析结果:")
                for key, value in result.items():
                    print(f"   {key}: {value}")
                return result
            else:
                logger.warning("未能解析到任何有效信息")
                print("❌ 未能解析到任何有效信息")
                # 即使没有其他信息，也要返回默认数量
                return {'quantity': '0'}

        except Exception as e:
            logger.error(f"获取SKU内容失败: {e}")
            return {}

    async def _check_browser_status(self) -> bool:
        """检查浏览器状态是否正常"""
        try:
            if not self.browser or not self.context or not self.page:
                logger.warning("浏览器组件不完整")
                return False

            # 检查浏览器是否已连接
            if self.browser.is_connected():
                # 尝试获取页面标题来验证页面是否可用
                await self.page.title()
                return True
            else:
                logger.warning("浏览器连接已断开")
                return False
        except Exception as e:
            logger.warning(f"浏览器状态检查失败: {e}")
            return False

    async def _ensure_browser_ready(self) -> bool:
        """确保浏览器准备就绪，如果不可用则重新初始化"""
        try:
            if await self._check_browser_status():
                return True

            logger.info("浏览器状态异常，尝试重新初始化...")

            # 先尝试关闭现有的浏览器实例
            await self._force_close_browser()

            # 重新初始化浏览器
            await self.init_browser()

            # 等待更长时间确保浏览器完全就绪
            await asyncio.sleep(2)

            # 再次检查状态
            if await self._check_browser_status():
                logger.info("浏览器重新初始化成功")
                return True
            else:
                logger.error("浏览器重新初始化失败")
                return False

        except Exception as e:
            logger.error(f"确保浏览器就绪失败: {e}")
            return False

    async def _force_close_browser(self):
        """强制关闭浏览器，忽略所有错误"""
        try:
            if self.page:
                try:
                    await self.page.close()
                except:
                    pass
                self.page = None

            if self.context:
                try:
                    await self.context.close()
                except:
                    pass
                self.context = None

            if self.browser:
                try:
                    await self.browser.close()
                except:
                    pass
                self.browser = None

            if self.playwright:
                try:
                    await self.playwright.stop()
                except:
                    pass
                self.playwright = None

        except Exception as e:
            logger.debug(f"强制关闭浏览器过程中的异常（可忽略）: {e}")

    async def close(self):
        """关闭浏览器"""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器失败: {e}")
            # 如果正常关闭失败，尝试强制关闭
            await self._force_close_browser()
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()


# 便捷函数
async def fetch_order_detail_simple(order_id: str, cookie_string: str = None, headless: bool = True, use_cache: bool = True) -> Optional[Dict[str, Any]]:
    """
    简单的订单详情获取函数（优化版：先检查数据库，再初始化浏览器）

    Args:
        order_id: 订单ID
        cookie_string: Cookie字符串，如果不提供则使用默认值
        headless: 是否无头模式

    Returns:
        订单详情字典，包含以下字段：
        - order_id: 订单ID
        - url: 订单详情页面URL
        - title: 页面标题
        - sku_info: 完整的SKU信息字典
        - spec_name: 规格名称
        - spec_value: 规格值
        - quantity: 数量
        - buyer_id: 买家ID
        - timestamp: 获取时间戳
        失败时返回None
    """
    if use_cache:
        # 先检查数据库中是否有有效数据
        try:
            from db_manager import db_manager
            existing_order = db_manager.get_order_by_id(order_id)

            if existing_order:
                cached_buyer_id = existing_order.get('buyer_id', '')
                if cached_buyer_id:
                    logger.info(f"📋 订单 {order_id} 已存在于数据库中且有买家ID，直接返回缓存数据")
                    print(f"✅ 订单 {order_id} 使用缓存数据，跳过浏览器获取")

                    result = {
                        'order_id': existing_order['order_id'],
                        'buyer_id': cached_buyer_id,
                        'url': f"https://www.goofish.com/order-detail?orderId={order_id}&role=seller",
                        'title': f"订单详情 - {order_id}",
                        'sku_info': {
                            'spec_name': existing_order.get('spec_name', ''),
                            'spec_value': existing_order.get('spec_value', ''),
                            'quantity': existing_order.get('quantity', '')
                        },
                        'spec_name': existing_order.get('spec_name', ''),
                        'spec_value': existing_order.get('spec_value', ''),
                        'quantity': existing_order.get('quantity', ''),
                        'order_status': existing_order.get('order_status', 'unknown'),
                        'timestamp': time.time(),
                        'from_cache': True
                    }
                    return result

                logger.info(f"📋 订单 {order_id} 已存在但买家ID为空，继续浏览器获取详情")
        except Exception as e:
            logger.warning(f"检查数据库缓存失败: {e}")

    # 数据库中没有有效数据，使用浏览器获取
    logger.info(f"🌐 订单 {order_id} 需要浏览器获取，开始初始化浏览器...")
    print(f"🔍 订单 {order_id} 开始浏览器获取详情...")

    fetcher = OrderDetailFetcher(cookie_string, headless)
    try:
        return await fetcher.fetch_order_detail(order_id, use_cache=use_cache)
    finally:
        await fetcher.close()
    return None


# 测试代码
if __name__ == "__main__":
    async def test():
        # 测试订单ID
        test_order_id = "2856024697612814489"
        
        print(f"🔍 开始获取订单详情: {test_order_id}")
        
        result = await fetch_order_detail_simple(test_order_id, headless=False)
        
        if result:
            print("✅ 订单详情获取成功:")
            print(f"📋 订单ID: {result['order_id']}")
            print(f"🌐 URL: {result['url']}")
            print(f"📄 页面标题: {result['title']}")
            print(f"👤 买家ID: {result.get('buyer_id', '未获取到')}")
            print(f"🛍️ 规格名称: {result.get('spec_name', '未获取到')}")
            print(f"📝 规格值: {result.get('spec_value', '未获取到')}")
            print(f"🔢 数量: {result.get('quantity', '未获取到')}")
        else:
            print("❌ 订单详情获取失败")
    
    # 运行测试
    asyncio.run(test())
