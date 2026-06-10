-- MySQL dump 10.13  Distrib 9.6.0, for macos26.2 (arm64)
--
-- Host: 127.0.0.1    Database: fastapiadmin
-- ------------------------------------------------------
-- Server version	8.4.3

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `app_portal`
--

DROP TABLE IF EXISTS `app_portal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `app_portal` (
  `name` varchar(64) NOT NULL COMMENT '应用名称',
  `access_url` varchar(500) NOT NULL COMMENT '访问地址',
  `icon_url` varchar(300) DEFAULT NULL COMMENT '应用图标URL',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `tenant_id` int NOT NULL COMMENT '租户ID',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_app_portal_uuid` (`uuid`),
  KEY `ix_app_portal_tenant_id` (`tenant_id`),
  KEY `ix_app_portal_deleted_id` (`deleted_id`),
  KEY `ix_app_portal_id` (`id`),
  KEY `ix_app_portal_created_id` (`created_id`),
  KEY `ix_app_portal_updated_time` (`updated_time`),
  KEY `ix_app_portal_is_deleted` (`is_deleted`),
  KEY `ix_app_portal_status` (`status`),
  KEY `ix_app_portal_updated_id` (`updated_id`),
  KEY `ix_app_portal_created_time` (`created_time`),
  KEY `ix_app_portal_deleted_time` (`deleted_time`),
  CONSTRAINT `app_portal_ibfk_1` FOREIGN KEY (`tenant_id`) REFERENCES `sys_tenant` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `app_portal_ibfk_2` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `app_portal_ibfk_3` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `app_portal_ibfk_4` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='门户应用';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `app_portal`
--

/*!40000 ALTER TABLE `app_portal` DISABLE KEYS */;
/*!40000 ALTER TABLE `app_portal` ENABLE KEYS */;

--
-- Table structure for table `apscheduler_jobs`
--

DROP TABLE IF EXISTS `apscheduler_jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `apscheduler_jobs` (
  `id` varchar(191) NOT NULL,
  `next_run_time` double DEFAULT NULL,
  `job_state` blob NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_apscheduler_jobs_next_run_time` (`next_run_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `apscheduler_jobs`
--

/*!40000 ALTER TABLE `apscheduler_jobs` DISABLE KEYS */;
/*!40000 ALTER TABLE `apscheduler_jobs` ENABLE KEYS */;

--
-- Table structure for table `gen_demo`
--

DROP TABLE IF EXISTS `gen_demo`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `gen_demo` (
  `name` varchar(64) NOT NULL COMMENT '名称',
  `a` int DEFAULT NULL COMMENT '整数',
  `b` bigint DEFAULT NULL COMMENT '大整数',
  `c` float DEFAULT NULL COMMENT '浮点数',
  `d` tinyint(1) NOT NULL COMMENT '布尔型',
  `e` date DEFAULT NULL COMMENT '日期',
  `f` time DEFAULT NULL COMMENT '时间',
  `g` datetime DEFAULT NULL COMMENT '日期时间',
  `h` text COMMENT '长文本',
  `i` json DEFAULT NULL COMMENT '元数据(JSON格式)',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_gen_demo_uuid` (`uuid`),
  KEY `ix_gen_demo_updated_id` (`updated_id`),
  KEY `ix_gen_demo_is_deleted` (`is_deleted`),
  KEY `ix_gen_demo_status` (`status`),
  KEY `ix_gen_demo_deleted_time` (`deleted_time`),
  KEY `ix_gen_demo_updated_time` (`updated_time`),
  KEY `ix_gen_demo_created_time` (`created_time`),
  KEY `ix_gen_demo_deleted_id` (`deleted_id`),
  KEY `ix_gen_demo_id` (`id`),
  KEY `ix_gen_demo_created_id` (`created_id`),
  CONSTRAINT `gen_demo_ibfk_1` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `gen_demo_ibfk_2` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `gen_demo_ibfk_3` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='示例表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `gen_demo`
--

/*!40000 ALTER TABLE `gen_demo` DISABLE KEYS */;
/*!40000 ALTER TABLE `gen_demo` ENABLE KEYS */;

--
-- Table structure for table `gen_demo01`
--

DROP TABLE IF EXISTS `gen_demo01`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `gen_demo01` (
  `name` varchar(64) NOT NULL COMMENT '名称',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_gen_demo01_uuid` (`uuid`),
  KEY `ix_gen_demo01_created_id` (`created_id`),
  KEY `ix_gen_demo01_updated_id` (`updated_id`),
  KEY `ix_gen_demo01_updated_time` (`updated_time`),
  KEY `ix_gen_demo01_id` (`id`),
  KEY `ix_gen_demo01_status` (`status`),
  KEY `ix_gen_demo01_is_deleted` (`is_deleted`),
  KEY `ix_gen_demo01_deleted_id` (`deleted_id`),
  KEY `ix_gen_demo01_created_time` (`created_time`),
  KEY `ix_gen_demo01_deleted_time` (`deleted_time`),
  CONSTRAINT `gen_demo01_ibfk_1` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `gen_demo01_ibfk_2` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `gen_demo01_ibfk_3` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='示例1表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `gen_demo01`
--

/*!40000 ALTER TABLE `gen_demo01` DISABLE KEYS */;
/*!40000 ALTER TABLE `gen_demo01` ENABLE KEYS */;

--
-- Table structure for table `gen_table`
--

DROP TABLE IF EXISTS `gen_table`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `gen_table` (
  `table_name` varchar(200) NOT NULL COMMENT '表名称',
  `table_comment` varchar(500) DEFAULT NULL COMMENT '表描述',
  `class_name` varchar(100) NOT NULL COMMENT '实体类名称',
  `package_name` varchar(100) DEFAULT NULL COMMENT '生成包路径',
  `module_name` varchar(30) DEFAULT NULL COMMENT '生成模块名',
  `business_name` varchar(30) DEFAULT NULL COMMENT '生成业务名',
  `function_name` varchar(100) DEFAULT NULL COMMENT '生成功能名',
  `sub_table_name` varchar(64) DEFAULT NULL COMMENT '关联子表的表名',
  `sub_table_fk_name` varchar(64) DEFAULT NULL COMMENT '子表关联的外键名',
  `parent_menu_id` int DEFAULT NULL COMMENT '父菜单ID',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_gen_table_uuid` (`uuid`),
  KEY `ix_gen_table_is_deleted` (`is_deleted`),
  KEY `ix_gen_table_id` (`id`),
  KEY `ix_gen_table_status` (`status`),
  KEY `ix_gen_table_deleted_id` (`deleted_id`),
  KEY `ix_gen_table_created_time` (`created_time`),
  KEY `ix_gen_table_deleted_time` (`deleted_time`),
  KEY `ix_gen_table_created_id` (`created_id`),
  KEY `ix_gen_table_updated_id` (`updated_id`),
  KEY `ix_gen_table_updated_time` (`updated_time`),
  CONSTRAINT `gen_table_ibfk_1` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `gen_table_ibfk_2` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `gen_table_ibfk_3` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='代码生成表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `gen_table`
--

/*!40000 ALTER TABLE `gen_table` DISABLE KEYS */;
/*!40000 ALTER TABLE `gen_table` ENABLE KEYS */;

--
-- Table structure for table `gen_table_column`
--

DROP TABLE IF EXISTS `gen_table_column`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `gen_table_column` (
  `column_name` varchar(200) NOT NULL COMMENT '列名称',
  `column_comment` varchar(500) DEFAULT NULL COMMENT '列描述',
  `column_type` varchar(100) NOT NULL COMMENT '列类型',
  `column_length` varchar(50) DEFAULT NULL COMMENT '列长度',
  `column_default` varchar(200) DEFAULT NULL COMMENT '列默认值',
  `is_pk` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否主键',
  `is_increment` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否自增',
  `is_nullable` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否允许为空',
  `is_unique` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否唯一',
  `python_type` varchar(100) DEFAULT NULL COMMENT 'Python类型',
  `python_field` varchar(200) DEFAULT NULL COMMENT 'Python字段名',
  `is_insert` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否为新增字段',
  `is_edit` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否编辑字段',
  `is_list` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否列表字段',
  `is_query` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否查询字段',
  `query_type` varchar(50) DEFAULT NULL COMMENT '查询方式',
  `html_type` varchar(100) DEFAULT NULL COMMENT '显示类型',
  `dict_type` varchar(200) DEFAULT NULL COMMENT '字典类型',
  `sort` int NOT NULL COMMENT '排序',
  `table_id` int NOT NULL COMMENT '归属表编号',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_gen_table_column_uuid` (`uuid`),
  KEY `ix_gen_table_column_created_time` (`created_time`),
  KEY `ix_gen_table_column_id` (`id`),
  KEY `ix_gen_table_column_deleted_id` (`deleted_id`),
  KEY `ix_gen_table_column_deleted_time` (`deleted_time`),
  KEY `ix_gen_table_column_table_id` (`table_id`),
  KEY `ix_gen_table_column_updated_time` (`updated_time`),
  KEY `ix_gen_table_column_created_id` (`created_id`),
  KEY `ix_gen_table_column_updated_id` (`updated_id`),
  KEY `ix_gen_table_column_is_deleted` (`is_deleted`),
  KEY `ix_gen_table_column_status` (`status`),
  CONSTRAINT `gen_table_column_ibfk_1` FOREIGN KEY (`table_id`) REFERENCES `gen_table` (`id`) ON DELETE CASCADE,
  CONSTRAINT `gen_table_column_ibfk_2` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `gen_table_column_ibfk_3` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `gen_table_column_ibfk_4` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='代码生成表字段';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `gen_table_column`
--

/*!40000 ALTER TABLE `gen_table_column` DISABLE KEYS */;
/*!40000 ALTER TABLE `gen_table_column` ENABLE KEYS */;

--
-- Table structure for table `sys_dept`
--

DROP TABLE IF EXISTS `sys_dept`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_dept` (
  `name` varchar(64) NOT NULL COMMENT '部门名称',
  `order` int NOT NULL COMMENT '显示排序',
  `code` varchar(16) NOT NULL COMMENT '部门编码',
  `leader` varchar(32) DEFAULT NULL COMMENT '部门负责人',
  `phone` varchar(11) DEFAULT NULL COMMENT '手机',
  `email` varchar(64) DEFAULT NULL COMMENT '邮箱',
  `parent_id` int DEFAULT NULL COMMENT '父级部门ID',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  UNIQUE KEY `ix_sys_dept_uuid` (`uuid`),
  KEY `ix_sys_dept_created_time` (`created_time`),
  KEY `ix_sys_dept_deleted_time` (`deleted_time`),
  KEY `ix_sys_dept_id` (`id`),
  KEY `ix_sys_dept_updated_time` (`updated_time`),
  KEY `ix_sys_dept_parent_id` (`parent_id`),
  KEY `ix_sys_dept_is_deleted` (`is_deleted`),
  KEY `ix_sys_dept_status` (`status`),
  CONSTRAINT `sys_dept_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `sys_dept` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='部门表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_dept`
--

/*!40000 ALTER TABLE `sys_dept` DISABLE KEYS */;
INSERT INTO `sys_dept` VALUES ('集团总公司',1,'GROUP','部门负责人','1582112620','deptadmin@example.com',NULL,1,'56dc9b76-42fd-46ed-926f-338e3baeb4d8','0','集团总公司','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL);
/*!40000 ALTER TABLE `sys_dept` ENABLE KEYS */;

--
-- Table structure for table `sys_dict_data`
--

DROP TABLE IF EXISTS `sys_dict_data`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_dict_data` (
  `dict_sort` int NOT NULL COMMENT '字典排序',
  `dict_label` varchar(255) NOT NULL COMMENT '字典标签',
  `dict_value` varchar(255) NOT NULL COMMENT '字典键值',
  `css_class` varchar(255) DEFAULT NULL COMMENT '样式属性（其他样式扩展）',
  `list_class` varchar(255) DEFAULT NULL COMMENT '表格回显样式',
  `is_default` tinyint(1) NOT NULL COMMENT '是否默认（True是 False否）',
  `dict_type` varchar(255) NOT NULL COMMENT '字典类型',
  `dict_type_id` int NOT NULL COMMENT '字典类型ID',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_sys_dict_data_uuid` (`uuid`),
  KEY `dict_type_id` (`dict_type_id`),
  KEY `ix_sys_dict_data_is_deleted` (`is_deleted`),
  KEY `ix_sys_dict_data_created_time` (`created_time`),
  KEY `ix_sys_dict_data_deleted_time` (`deleted_time`),
  KEY `ix_sys_dict_data_status` (`status`),
  KEY `ix_sys_dict_data_id` (`id`),
  KEY `ix_sys_dict_data_updated_time` (`updated_time`),
  CONSTRAINT `sys_dict_data_ibfk_1` FOREIGN KEY (`dict_type_id`) REFERENCES `sys_dict_type` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=35 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='字典数据表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_dict_data`
--

/*!40000 ALTER TABLE `sys_dict_data` DISABLE KEYS */;
INSERT INTO `sys_dict_data` VALUES (1,'男','0','blue',NULL,1,'sys_user_sex',1,1,'ead026d6-ebbc-4cab-8f4a-b3a08428550a','0','性别男','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(2,'女','1','pink',NULL,0,'sys_user_sex',1,2,'ab57690c-5dcb-417f-8968-402f7829d7f6','0','性别女','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(3,'未知','2','red',NULL,0,'sys_user_sex',1,3,'d2ff0cbf-1e16-4c97-af3c-d25293e509a4','0','性别未知','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(1,'是','1','','primary',1,'sys_yes_no',2,4,'31467a4b-002a-4b16-9a8a-c8f9eb2f5fac','0','是','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(2,'否','0','','danger',0,'sys_yes_no',2,5,'445cc34f-d67c-4d22-a855-debb223f9dca','0','否','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(1,'启用','1','','primary',0,'sys_common_status',3,6,'0802efa8-c2f7-45ba-b198-d94276d9b58e','0','启用状态','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(2,'停用','0','','danger',0,'sys_common_status',3,7,'35ce823b-53d0-4fa5-a74d-39c925056f8a','0','停用状态','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(1,'通知','1','blue','warning',1,'sys_notice_type',4,8,'a9f1c4c5-e9ee-4ff9-a3ad-da2d62c170b3','0','通知','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(2,'公告','2','orange','success',0,'sys_notice_type',4,9,'8fb1c0a0-bd34-47a2-9f1a-ee3de06aa60f','0','公告','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(99,'其他','0','','info',0,'sys_oper_type',5,10,'48bd9447-4969-41c5-91a0-0a67e44dad70','0','其他操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(1,'新增','1','','info',0,'sys_oper_type',5,11,'921ac674-5d9a-404f-8b5f-6120735c31e3','0','新增操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(2,'修改','2','','info',0,'sys_oper_type',5,12,'9549e176-0cfa-404a-8f03-3d44c9cc445a','0','修改操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(3,'删除','3','','danger',0,'sys_oper_type',5,13,'bec62942-20b5-4414-8bb3-b19f6ca5e44c','0','删除操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(4,'分配权限','4','','primary',0,'sys_oper_type',5,14,'9b21a775-4567-4fbb-a37e-a0c209a66b0a','0','授权操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(5,'导出','5','','warning',0,'sys_oper_type',5,15,'e825beb1-f7f9-487b-a5cc-88c218192746','0','导出操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(6,'导入','6','','warning',0,'sys_oper_type',5,16,'0a7feda3-6bd6-4db9-84e1-2384592122ae','0','导入操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(7,'强退','7','','danger',0,'sys_oper_type',5,17,'2b5ccfe4-9b6b-46de-88ac-cb84513fa2cb','0','强退操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(8,'生成代码','8','','warning',0,'sys_oper_type',5,18,'0f91738c-c641-46f8-b1b8-6d0a2ebe3557','0','生成操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(9,'清空数据','9','','danger',0,'sys_oper_type',5,19,'3825064a-7395-4ebe-9be0-39a898c988d9','0','清空操作','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(1,'默认(Memory)','default','',NULL,1,'sys_job_store',6,20,'ec588f67-0d5e-4cfd-b82f-f98f21f3e9d6','0','默认分组','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(2,'数据库(Sqlalchemy)','sqlalchemy','',NULL,0,'sys_job_store',6,21,'8ad85176-f0d4-4f56-8309-fc1db5f1feec','0','数据库分组','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(3,'数据库(Redis)','redis','',NULL,0,'sys_job_store',6,22,'cdca473c-1ab6-4768-9f7f-c309cbf25987','0','reids分组','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(1,'线程池','default','',NULL,0,'sys_job_executor',7,23,'88aff073-9ee5-4eef-a0ff-8b9fe3e116c6','0','线程池','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(2,'进程池','processpool','',NULL,0,'sys_job_executor',7,24,'822b38ad-7037-4437-8f96-52208d3033b8','0','进程池','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(1,'演示函数','scheduler_test.job','',NULL,1,'sys_job_function',8,25,'56387275-cacb-4424-8c23-f9dc74be8466','0','演示函数','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(1,'指定日期(date)','date','',NULL,1,'sys_job_trigger',9,26,'0a920e70-03bf-4d17-8155-ba7fa9a37be8','0','指定日期任务触发器','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(2,'间隔触发器(interval)','interval','',NULL,0,'sys_job_trigger',9,27,'8acdb56a-d66a-4434-8b05-4fc565b7a529','0','间隔触发器任务触发器','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(3,'cron表达式','cron','',NULL,0,'sys_job_trigger',9,28,'b0160052-cb67-49b1-9112-29cb5b0c1231','0','间隔触发器任务触发器','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(1,'默认(default)','default','',NULL,1,'sys_list_class',10,29,'8fbe9bdd-e9cd-4d7b-8043-aa5398e91a69','0','默认表格回显样式','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(2,'主要(primary)','primary','',NULL,0,'sys_list_class',10,30,'695e0c0c-716d-4aad-b4e6-fcf0f8ef156a','0','主要表格回显样式','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(3,'成功(success)','success','',NULL,0,'sys_list_class',10,31,'232abc32-3627-4b8c-bb6f-b9473876f572','0','成功表格回显样式','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(4,'信息(info)','info','',NULL,0,'sys_list_class',10,32,'90fb0cd2-f73c-4d64-b69e-0328e20ee3fa','0','信息表格回显样式','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(5,'警告(warning)','warning','',NULL,0,'sys_list_class',10,33,'5a7a9357-c2f6-4561-ba4c-e3e47fd5e4bb','0','警告表格回显样式','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),(6,'危险(danger)','danger','',NULL,0,'sys_list_class',10,34,'5f153fb8-c88f-4894-ac74-3ad3502b5dcb','0','危险表格回显样式','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL);
/*!40000 ALTER TABLE `sys_dict_data` ENABLE KEYS */;

--
-- Table structure for table `sys_dict_type`
--

DROP TABLE IF EXISTS `sys_dict_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_dict_type` (
  `dict_name` varchar(64) NOT NULL COMMENT '字典名称',
  `dict_type` varchar(255) NOT NULL COMMENT '字典类型',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `dict_type` (`dict_type`),
  UNIQUE KEY `ix_sys_dict_type_uuid` (`uuid`),
  KEY `ix_sys_dict_type_id` (`id`),
  KEY `ix_sys_dict_type_updated_time` (`updated_time`),
  KEY `ix_sys_dict_type_is_deleted` (`is_deleted`),
  KEY `ix_sys_dict_type_status` (`status`),
  KEY `ix_sys_dict_type_deleted_time` (`deleted_time`),
  KEY `ix_sys_dict_type_created_time` (`created_time`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='字典类型表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_dict_type`
--

/*!40000 ALTER TABLE `sys_dict_type` DISABLE KEYS */;
INSERT INTO `sys_dict_type` VALUES ('用户性别','sys_user_sex',1,'594617a3-60e0-47e7-b4db-b5ab4841fafb','0','用户性别列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('系统是否','sys_yes_no',2,'df24dea6-76c6-4532-a8b0-d3c674d69f39','0','系统是否列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('系统状态','sys_common_status',3,'7c10ed3c-4a27-4aa5-9aa8-1ee5560701ac','0','系统状态','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('通知类型','sys_notice_type',4,'a962d449-3fce-46ba-8a6f-746912616681','0','通知类型列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('操作类型','sys_oper_type',5,'fe5012ab-b281-4b99-acbc-4f5131284ec4','0','操作类型列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('任务存储器','sys_job_store',6,'e2875ab6-fe73-48da-ab9f-3435c0988207','0','任务分组列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('任务执行器','sys_job_executor',7,'9cc2fcee-874a-4e7e-b0c5-21379fd36668','0','任务执行器列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('任务函数','sys_job_function',8,'74fe593c-45b7-4e44-b1fd-529f7cac5844','0','任务函数列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('任务触发器','sys_job_trigger',9,'0e77676b-eb29-4571-8177-ecb55c6583b8','0','任务触发器列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('表格回显样式','sys_list_class',10,'a1d0915f-e78f-42af-be6c-b256244d938c','0','表格回显样式列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL);
/*!40000 ALTER TABLE `sys_dict_type` ENABLE KEYS */;

--
-- Table structure for table `sys_log`
--

DROP TABLE IF EXISTS `sys_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_log` (
  `type` int NOT NULL COMMENT '日志类型(1登录日志 2操作日志)',
  `request_path` varchar(255) NOT NULL COMMENT '请求路径',
  `request_method` varchar(10) NOT NULL COMMENT '请求方式',
  `request_payload` longtext COMMENT '请求体',
  `request_ip` varchar(50) DEFAULT NULL COMMENT '请求IP地址',
  `login_location` varchar(255) DEFAULT NULL COMMENT '登录位置',
  `request_os` varchar(64) DEFAULT NULL COMMENT '操作系统',
  `request_browser` varchar(64) DEFAULT NULL COMMENT '浏览器',
  `response_code` int NOT NULL COMMENT '响应状态码',
  `response_json` longtext COMMENT '响应体',
  `process_time` varchar(20) DEFAULT NULL COMMENT '处理时间',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_sys_log_uuid` (`uuid`),
  KEY `ix_sys_log_is_deleted` (`is_deleted`),
  KEY `ix_sys_log_status` (`status`),
  KEY `ix_sys_log_created_id` (`created_id`),
  KEY `ix_sys_log_updated_time` (`updated_time`),
  KEY `ix_sys_log_updated_id` (`updated_id`),
  KEY `ix_sys_log_deleted_id` (`deleted_id`),
  KEY `ix_sys_log_created_time` (`created_time`),
  KEY `ix_sys_log_deleted_time` (`deleted_time`),
  KEY `ix_sys_log_id` (`id`),
  CONSTRAINT `sys_log_ibfk_1` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `sys_log_ibfk_2` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `sys_log_ibfk_3` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='系统日志表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_log`
--

/*!40000 ALTER TABLE `sys_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `sys_log` ENABLE KEYS */;

--
-- Table structure for table `sys_menu`
--

DROP TABLE IF EXISTS `sys_menu`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_menu` (
  `name` varchar(50) NOT NULL COMMENT '菜单名称',
  `type` int NOT NULL COMMENT '菜单类型(1:目录 2:菜单 3:按钮/权限 4:链接)',
  `order` int NOT NULL COMMENT '显示排序',
  `permission` varchar(100) DEFAULT NULL COMMENT '权限标识(如:module_system:user:query)',
  `icon` varchar(50) DEFAULT NULL COMMENT '菜单图标',
  `route_name` varchar(100) DEFAULT NULL COMMENT '路由名称',
  `route_path` varchar(200) DEFAULT NULL COMMENT '路由路径',
  `component_path` varchar(200) DEFAULT NULL COMMENT '组件路径',
  `redirect` varchar(200) DEFAULT NULL COMMENT '重定向地址',
  `hidden` tinyint(1) NOT NULL COMMENT '是否隐藏(True:隐藏 False:显示)',
  `keep_alive` tinyint(1) NOT NULL COMMENT '是否缓存(True:是 False:否)',
  `always_show` tinyint(1) NOT NULL COMMENT '是否始终显示(True:是 False:否)',
  `title` varchar(50) DEFAULT NULL COMMENT '菜单标题',
  `params` json DEFAULT NULL COMMENT '路由参数(JSON对象)',
  `affix` tinyint(1) NOT NULL COMMENT '是否固定标签页(True:是 False:否)',
  `parent_id` int DEFAULT NULL COMMENT '父菜单ID',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_sys_menu_uuid` (`uuid`),
  KEY `ix_sys_menu_created_time` (`created_time`),
  KEY `ix_sys_menu_deleted_time` (`deleted_time`),
  KEY `ix_sys_menu_id` (`id`),
  KEY `ix_sys_menu_parent_id` (`parent_id`),
  KEY `ix_sys_menu_updated_time` (`updated_time`),
  KEY `ix_sys_menu_is_deleted` (`is_deleted`),
  KEY `ix_sys_menu_status` (`status`),
  CONSTRAINT `sys_menu_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `sys_menu` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB AUTO_INCREMENT=189 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='菜单表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_menu`
--

/*!40000 ALTER TABLE `sys_menu` DISABLE KEYS */;
INSERT INTO `sys_menu` VALUES ('仪表盘',1,1,'','client','Dashboard','/dashboard',NULL,'/dashboard/workplace',0,1,1,'仪表盘','null',0,NULL,1,'6cb966e0-52a3-4a2f-a280-77e9bf50b0ad','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('系统管理',1,2,NULL,'system','System','/system',NULL,'/system/menu',0,1,0,'系统管理','null',0,NULL,2,'3a8e68f8-80f7-4edd-bbcb-8180d65c7a7c','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('监控管理',1,3,NULL,'monitor','Monitor','/monitor',NULL,'/monitor/online',0,1,0,'监控管理','null',0,NULL,3,'e6e0d392-17aa-4882-8847-9b190fe53690','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('接口管理',1,4,NULL,'document','Common','/common',NULL,'/common/docs',0,1,0,'接口管理','null',0,NULL,4,'40026226-75bd-4584-b6b2-7142b13a27da','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('代码管理',1,5,NULL,'code','Generator','/generator',NULL,'/generator/gencode',0,1,0,'代码管理','null',0,NULL,5,'8a2e3ec0-9db7-4a6c-ae55-32a910614ec8','0','代码管理','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('应用管理',1,6,NULL,'el-icon-ShoppingBag','Application','/application',NULL,'/application/portal',0,1,0,'应用管理','null',0,NULL,6,'82f85cf2-63e1-419e-9ee4-c3dab3b07415','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('AI管理',1,7,NULL,'el-icon-ChatLineSquare','AI','/ai',NULL,'/ai/chat',0,1,0,'AI管理','null',0,NULL,7,'22bc23ab-9d7f-4920-902b-8305fe1468e8','0','AI管理','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('任务管理',1,8,NULL,'el-icon-SetUp','Task','/task',NULL,'/task/cronjob/job',0,1,0,'任务管理','null',0,NULL,8,'7394ad16-772c-4cc8-95f2-8e85877b84e9','0','任务管理','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('案例管理',1,9,NULL,'menu','Example','/example',NULL,'/example/demo',0,1,0,'案例管理','null',0,NULL,9,'2b7b2965-8933-41ea-abb1-483b36e496b2','0','案例管理','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('工作台',2,1,'dashboard:workplace:query','el-icon-PieChart','Workplace','/dashboard/workplace','dashboard/workplace',NULL,0,1,0,'工作台','null',0,1,10,'da4c6db8-6921-483e-958b-c85991a03472','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('菜单管理',2,1,'module_system:menu:query','menu','Menu','/system/menu','module_system/menu/index',NULL,0,1,0,'菜单管理','null',0,2,11,'389f8ec5-98a0-46bd-ac82-0c735a39597e','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('部门管理',2,2,'module_system:dept:query','tree','Dept','/system/dept','module_system/dept/index',NULL,0,1,0,'部门管理','null',0,2,12,'33290cf6-b54b-4be6-ab8f-398b7e55ba14','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('岗位管理',2,3,'module_system:position:query','el-icon-Coordinate','Position','/system/position','module_system/position/index',NULL,0,1,0,'岗位管理','null',0,2,13,'0673ff55-6816-4922-a09e-d6cc729dc863','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('角色管理',2,4,'module_system:role:query','role','Role','/system/role','module_system/role/index',NULL,0,1,0,'角色管理','null',0,2,14,'b8d497eb-cb41-4a43-8780-50b927240cf7','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('用户管理',2,5,'module_system:user:query','el-icon-User','User','/system/user','module_system/user/index',NULL,0,1,0,'用户管理','null',0,2,15,'4a868dde-df3f-4fa5-8067-bcefb4547cca','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('日志管理',2,6,'module_system:log:query','el-icon-Aim','Log','/system/log','module_system/log/index',NULL,0,1,0,'日志管理','null',0,2,16,'d65047da-93ef-4431-84e9-41d7507402c1','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('公告管理',2,7,'module_system:notice:query','bell','Notice','/system/notice','module_system/notice/index',NULL,0,1,0,'公告管理','null',0,2,17,'a4f06d77-342a-431a-9376-9ce9824e97d6','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('参数管理',2,8,'module_system:param:query','setting','Params','/system/param','module_system/param/index',NULL,0,1,0,'参数管理','null',0,2,18,'64211f1e-9699-482d-900f-e749a3acf709','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('字典管理',2,9,'module_system:dict_type:query','dict','Dict','/system/dict','module_system/dict/index',NULL,0,1,0,'字典管理','null',0,2,19,'e78c0ca4-ab52-461b-9f6b-39c094061094','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('租户管理',2,10,'module_system:tenant:query','el-icon-DataBoard','Tenant','/system/tenant','module_system/tenant/index',NULL,0,1,0,'租户管理','null',0,2,20,'60b0f167-322e-414f-9a0b-4e54f26bb3b4','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('在线用户',2,1,'module_monitor:online:query','el-icon-Headset','MonitorOnline','/monitor/online','module_monitor/online/index',NULL,0,1,0,'在线用户','null',0,3,21,'e8333cd0-97c8-4e07-82fa-d32833263f88','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('服务器监控',2,2,'module_monitor:server:query','el-icon-Odometer','MonitorServer','/monitor/server','module_monitor/server/index',NULL,0,1,0,'服务器监控','null',0,3,22,'ab15ab54-7a82-4de3-b30c-ee4dd42cb386','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('缓存监控',2,3,'module_monitor:cache:query','el-icon-Stopwatch','MonitorCache','/monitor/cache','module_monitor/cache/index',NULL,0,1,0,'缓存监控','null',0,3,23,'0f82a055-e6bf-444d-b989-92ebe3b5db09','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('文件管理',2,4,'module_monitor:resource:query','el-icon-Files','Resource','/monitor/resource','module_monitor/resource/index',NULL,0,1,0,'文件管理','null',0,3,24,'2e2bf547-5df2-4d33-8bd7-b7b7d2ce027a','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('Swagger文档',4,1,'module_common:docs:query','api','Docs','/common/docs','module_common/docs/index',NULL,0,1,0,'Swagger文档','null',0,4,25,'fbd3f238-949d-41f6-bee1-c3695fc0045d','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('Redoc文档',4,2,'module_common:redoc:query','el-icon-Document','Redoc','/common/redoc','module_common/redoc/index',NULL,0,1,0,'Redoc文档','null',0,4,26,'1f137ab5-d7f7-49c1-bc27-1cb8ce57744f','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('LangJin文档',4,3,'module_common:ljdoc:query','el-icon-Document','Ljdoc','/common/ljdoc','module_common/ljdoc/index',NULL,0,1,0,'LangJin文档','null',0,4,27,'d62856bf-12c5-46de-8ed4-1f8e25591f66','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('代码生成',2,1,'module_generator:gencode:query','code','GenCode','/generator/gencode','module_generator/gencode/index',NULL,0,1,0,'代码生成','null',0,5,28,'9c59374c-9978-4db4-b9f2-4a01dcbf951e','0','代码生成','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('插件市场',2,1,'module_application:portal:query','el-icon-ShoppingCartFull','PortalApp','/application/portal','module_application/portal/index',NULL,0,1,0,'插件市场','null',0,6,29,'14bb83f3-f9f3-499b-8eb3-37e6a2488719','0','初始化数据','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('AI智能助手',2,1,'module_ai:chat:query','el-icon-ChatDotRound','Chat','/ai/chat','module_ai/chat/index',NULL,0,1,0,'AI智能助手','null',0,7,30,'1885602f-7853-4c0c-99f7-55dd68ab3333','0','AI智能助手','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('会话记忆',2,2,'module_ai:chat:query','el-icon-ChatLineSquare','Memory','/ai/memory','module_ai/memory/index',NULL,0,1,0,'会话记忆','null',0,7,31,'bc3db703-1d65-4e0c-852e-2b240ec7f112','0','会话记忆管理','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL),('定时任务',1,1,NULL,'el-icon-Timer','Cronjob','/task/cronjob',NULL,'/task/cronjob/job',0,1,1,'定时任务','null',0,8,32,'7c3e1e64-1091-4a46-89e0-6c798d1304a5','0','APScheduler 调度器与任务节点','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('工作流',1,2,NULL,'el-icon-SetUp','WorkflowMgr','/task/workflow-mgr',NULL,'/task/workflow/definition',0,1,1,'工作流','null',0,8,33,'67633e81-a7b4-48b4-99aa-c4d8ccb49284','0','流程编排与编排节点类型','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('示例管理',2,1,'module_example:demo:query','menu','Demo','/example/demo','module_example/demo/index',NULL,0,1,0,'示例管理','null',0,9,34,'ebe962dc-ccde-4d86-a57d-d4ea7023069b','0','示例管理','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('二级目录',1,2,NULL,'menu','DemoDir','/example/demo-group',NULL,'/example/demo-group/demo01',0,1,1,'二级目录','null',0,9,35,'6f2e9de1-656c-4bb0-988c-cc33e0e66729','0','二级目录（含三级菜单）','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建菜单',3,1,'module_system:menu:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建菜单','null',0,11,36,'a0054d3d-0990-4b15-8387-c11237afda5e','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改菜单',3,2,'module_system:menu:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改菜单','null',0,11,37,'50f0f12c-14e3-4d74-ba52-ccfa290e39ab','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除菜单',3,3,'module_system:menu:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除菜单','null',0,11,38,'7ca45849-31e0-4e4f-a690-2e2c428a3257','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改菜单状态',3,4,'module_system:menu:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改菜单状态','null',0,11,39,'b7e72856-e2ba-404d-ba0d-acb8eb40c919','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情菜单',3,5,'module_system:menu:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情菜单','null',0,11,40,'fc218507-0554-4a1b-8edb-42996d916c46','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询菜单',3,6,'module_system:menu:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询菜单','null',0,11,41,'c15955c8-49f2-44ff-91bc-15d17601eb24','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建部门',3,1,'module_system:dept:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建部门','null',0,12,42,'85b89f89-1ad0-4b12-96b0-19211d1844c6','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改部门',3,2,'module_system:dept:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改部门','null',0,12,43,'022604d6-e7f6-4ba7-9f8b-5a18ab7c0f5f','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除部门',3,3,'module_system:dept:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除部门','null',0,12,44,'4fac4f2c-806e-43a4-be9d-f17a8bec99a8','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改部门状态',3,4,'module_system:dept:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改部门状态','null',0,12,45,'27307275-44e5-4817-a61f-46376f2007e9','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情部门',3,5,'module_system:dept:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情部门','null',0,12,46,'ecc82941-07b1-4ef6-b563-f8d95061060a','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询部门',3,6,'module_system:dept:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询部门','null',0,12,47,'a7a93e71-e921-4237-a217-7c750fce96e3','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建岗位',3,1,'module_system:position:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建岗位','null',0,13,48,'a9554479-7030-4ea5-80ea-f2fa561d53da','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改岗位',3,2,'module_system:position:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改岗位','null',0,13,49,'84bf1943-f3a8-4ac9-9bce-f4bce2073b55','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除岗位',3,3,'module_system:position:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改岗位','null',0,13,50,'ba03904e-2374-4a78-92d6-a378b464de6a','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改岗位状态',3,4,'module_system:position:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改岗位状态','null',0,13,51,'665d7812-ecb5-4a75-b497-3fcfc77fb9fc','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('岗位导出',3,5,'module_system:position:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'岗位导出','null',0,13,52,'c8ad7656-5906-4bb5-845e-24828bfe1c55','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情岗位',3,6,'module_system:position:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情岗位','null',0,13,53,'d2a3c03a-3a15-476f-ad7a-0687cee10ad1','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询岗位',3,7,'module_system:position:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询岗位','null',0,13,54,'339ecf99-7dcf-4f1c-a6bb-d74a29b93956','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建角色',3,1,'module_system:role:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建角色','null',0,14,55,'6a020f29-47e5-4f52-a8ef-b20348575831','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改角色',3,2,'module_system:role:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改角色','null',0,14,56,'63552e70-7d4f-4827-a960-a1ac28d3de6a','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除角色',3,3,'module_system:role:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除角色','null',0,14,57,'45f12c3d-4045-4335-97a6-228133e202ed','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改角色状态',3,4,'module_system:role:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改角色状态','null',0,14,58,'9c4493a5-e8f7-4020-854c-663a16a5356c','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('角色导出',3,5,'module_system:role:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'角色导出','null',0,14,59,'22711711-e922-4729-bea2-bde54d3d8323','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情角色',3,6,'module_system:role:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情角色','null',0,14,60,'688d0096-830b-4f2b-a372-41c9c2ad0f19','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询角色',3,7,'module_system:role:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询角色','null',0,14,61,'328b759d-8769-44ed-80d2-25dd81741e2a','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('分配权限',3,8,'module_system:role:permission',NULL,NULL,NULL,NULL,NULL,0,1,0,'分配权限','null',0,14,62,'f154ed74-8b3f-49cb-9aa0-0e3801156bc3','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建用户',3,1,'module_system:user:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建用户','null',0,15,63,'2d9cb0e3-6c2b-4a55-831d-c1db265aca65','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改用户',3,2,'module_system:user:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改用户','null',0,15,64,'adb7c7fc-41e0-469b-a5d5-0ebf9bf06223','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除用户',3,3,'module_system:user:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除用户','null',0,15,65,'d5cb6262-b96f-42d4-93f8-4fa550709412','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改用户状态',3,4,'module_system:user:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改用户状态','null',0,15,66,'859fc1ab-cf52-49e3-8b86-ab4b27a3b1b6','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导出用户',3,5,'module_system:user:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'导出用户','null',0,15,67,'4beeb289-4b49-4fbe-88c4-3d81989d778c','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导入用户',3,6,'module_system:user:import',NULL,NULL,NULL,NULL,NULL,0,1,0,'导入用户','null',0,15,68,'b5a26242-9747-4feb-bf1e-bf8887914d74','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('下载用户导入模板',3,7,'module_system:user:download',NULL,NULL,NULL,NULL,NULL,0,1,0,'下载用户导入模板','null',0,15,69,'9aea32ea-0b68-447f-80ab-fad22ecd9c1d','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情用户',3,8,'module_system:user:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情用户','null',0,15,70,'5e763bc8-d398-495e-aa4a-0d6799139067','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询用户',3,9,'module_system:user:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询用户','null',0,15,71,'8b81e489-5c8e-4149-88bc-77a29c2a108c','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('日志删除',3,1,'module_system:log:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'日志删除','null',0,16,72,'690acf81-1995-4e29-9187-b1f9d67159d8','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('日志导出',3,2,'module_system:log:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'日志导出','null',0,16,73,'e2f038e5-5990-4c5c-b3b6-489346dce2c9','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('日志详情',3,3,'module_system:log:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'日志详情','null',0,16,74,'8cb9bdc6-f250-4a17-b9b1-a49f19f384dc','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询日志',3,4,'module_system:log:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询日志','null',0,16,75,'6541e335-ea9a-4e20-a32f-3bb41e5f8cd5','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('公告创建',3,1,'module_system:notice:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'公告创建','null',0,17,76,'5e5bcfad-1526-405d-a27b-465907a63828','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('公告修改',3,2,'module_system:notice:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改用户','null',0,17,77,'b16883b5-b44a-4f97-a51e-76aba0a50dd2','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('公告删除',3,3,'module_system:notice:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'公告删除','null',0,17,78,'3bdb81a2-d1af-466c-b6cb-24ca735378da','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('公告导出',3,4,'module_system:notice:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'公告导出','null',0,17,79,'ff1854fc-91ad-489a-a491-e14f44cdba28','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('公告批量修改状态',3,5,'module_system:notice:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'公告批量修改状态','null',0,17,80,'cbba57a8-534a-49e7-9ae8-4f3ed18a5918','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('公告详情',3,6,'module_system:notice:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'公告详情','null',0,17,81,'bfc58fea-2343-4a40-817b-c476c2cc8709','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询公告',3,5,'module_system:notice:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询公告','null',0,17,82,'ac711c3e-8e30-43fb-809d-e99085bf1707','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建参数',3,1,'module_system:param:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建参数','null',0,18,83,'2ced219d-c33e-4782-9cb9-98bc5bd4415f','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改参数',3,2,'module_system:param:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改参数','null',0,18,84,'43f6a79f-992f-4a29-9c29-69b24ea7ffc4','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除参数',3,3,'module_system:param:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除参数','null',0,18,85,'2c023ce7-6aa4-44b9-8b1f-4d04975073e5','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导出参数',3,4,'module_system:param:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'导出参数','null',0,18,86,'bc9f4b4a-d5e6-4310-97db-a25ea544207b','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('参数上传',3,5,'module_system:param:upload',NULL,NULL,NULL,NULL,NULL,0,1,0,'参数上传','null',0,18,87,'52452e4d-24ca-469a-8a86-eac32412e36e','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('参数详情',3,6,'module_system:param:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'参数详情','null',0,18,88,'506fef7c-fa3d-49ba-bc52-c3c1a4e3c525','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询参数',3,7,'module_system:param:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询参数','null',0,18,89,'f9cf6581-db34-4b5b-baea-09c25b879f8d','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建字典类型',3,1,'module_system:dict_type:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建字典类型','null',0,19,90,'dfadff99-941c-4ade-94f4-163ecc6c0a73','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改字典类型',3,2,'module_system:dict_type:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改字典类型','null',0,19,91,'f4a01b12-e187-47af-b51e-63a3916fc78e','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除字典类型',3,3,'module_system:dict_type:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除字典类型','null',0,19,92,'2f4b5bce-7a51-4b09-9589-e0488962e0a4','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导出字典类型',3,4,'module_system:dict_type:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'导出字典类型','null',0,19,93,'bde23ad2-75bb-4af1-aa4a-d1a1120d6ff7','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改字典状态',3,5,'module_system:dict_type:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'导出字典类型','null',0,19,94,'21949596-92ab-45e7-a9dd-84f7df2302ea','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('字典数据查询',3,6,'module_system:dict_data:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'字典数据查询','null',0,19,95,'a19826a8-adb8-4630-8560-be5270bd8550','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建字典数据',3,7,'module_system:dict_data:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建字典数据','null',0,19,96,'5f883077-2317-4cec-ba7e-aa4fa8eef673','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改字典数据',3,8,'module_system:dict_data:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改字典数据','null',0,19,97,'494b67a5-f624-452b-9907-2cb9546a08c1','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除字典数据',3,9,'module_system:dict_data:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除字典数据','null',0,19,98,'2e1c31ad-f23a-4066-b5ae-686f54606fda','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导出字典数据',3,10,'module_system:dict_data:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'导出字典数据','null',0,19,99,'2253bf70-acb1-40aa-b1ec-7b227ab1160d','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改字典数据状态',3,11,'module_system:dict_data:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改字典数据状态','null',0,19,100,'27b1d7b7-9628-436b-aaf1-4781724fc3c0','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情字典类型',3,12,'module_system:dict_type:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情字典类型','null',0,19,101,'4ae662c1-7739-44d3-bae9-97031569a5dc','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询字典类型',3,13,'module_system:dict_type:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询字典类型','null',0,19,102,'2fbe12da-8469-47f9-9c81-a477345e5911','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情字典数据',3,14,'module_system:dict_data:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情字典数据','null',0,19,103,'9df007c4-d927-445f-9532-c007d82baab2','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建租户',3,1,'module_system:tenant:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建租户','null',0,20,104,'4edb3b45-bd3b-4a0b-aeaa-ed8287b74fc9','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改租户',3,2,'module_system:tenant:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改租户','null',0,20,105,'e41ebf4b-6c91-479d-b82c-1bf5571340a4','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除租户',3,3,'module_system:tenant:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除租户','null',0,20,106,'17df6bbe-ea34-4404-9e08-fbdd34825ad5','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改租户状态',3,4,'module_system:tenant:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改租户状态','null',0,20,107,'cbb706cb-efc8-4861-b563-48ec35bf9afa','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('租户详情',3,5,'module_system:tenant:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'租户详情','null',0,20,108,'9f08fd60-a512-47be-a907-c247d914f048','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询租户',3,6,'module_system:tenant:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询租户','null',0,20,109,'65e632b6-2ab5-4800-9d61-210b106c4346','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('在线用户强制下线',3,1,'module_monitor:online:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'在线用户强制下线','null',0,21,110,'02ac4f77-eac6-4d0b-a7bb-3d5ba52f700d','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('清除缓存',3,1,'module_monitor:cache:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'清除缓存','null',0,23,111,'f6faebdd-bcf3-436e-adfc-fcac562ab236','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('文件上传',3,1,'module_monitor:resource:upload',NULL,NULL,NULL,NULL,NULL,0,1,0,'文件上传','null',0,24,112,'65231682-fd9e-4773-a682-5b0a502849eb','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('文件下载',3,2,'module_monitor:resource:download',NULL,NULL,NULL,NULL,NULL,0,1,0,'文件下载','null',0,24,113,'483e374c-80ed-4548-9b2d-ba6a45945f92','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('文件删除',3,3,'module_monitor:resource:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'文件删除','null',0,24,114,'31912369-dda7-4b2c-8de8-4f6da580bde7','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('文件移动',3,4,'module_monitor:resource:move',NULL,NULL,NULL,NULL,NULL,0,1,0,'文件移动','null',0,24,115,'95c3e9cf-7080-45bf-bb1a-c0c3c84c8ee1','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('文件复制',3,5,'module_monitor:resource:copy',NULL,NULL,NULL,NULL,NULL,0,1,0,'文件复制','null',0,24,116,'150da577-5e22-412a-ae5d-a2db8112cfa2','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('文件重命名',3,6,'module_monitor:resource:rename',NULL,NULL,NULL,NULL,NULL,0,1,0,'文件重命名','null',0,24,117,'0911ce45-7db2-4500-8e7f-0149b6ac265c','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建目录',3,7,'module_monitor:resource:create_dir',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建目录','null',0,24,118,'907dcf81-0a78-4008-8635-74de9e16bced','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导出文件列表',3,9,'module_monitor:resource:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'导出文件列表','null',0,24,119,'891d6527-e8c6-40bc-8ead-dbee4c418b81','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询代码生成业务表列表',3,1,'module_generator:gencode:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询代码生成业务表列表','null',0,28,120,'27c7e787-1d69-412c-bbef-27983b451ad1','0','查询代码生成业务表列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建表结构',3,2,'module_generator:gencode:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建表结构','null',0,28,121,'150aaea8-be6c-403f-ae32-53506879addb','0','创建表结构','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('编辑业务表信息',3,3,'module_generator:gencode:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'编辑业务表信息','null',0,28,122,'98e22808-f4b0-4436-968b-a6869f7274f0','0','编辑业务表信息','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除业务表信息',3,4,'module_generator:gencode:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除业务表信息','null',0,28,123,'ab8805f0-de52-404a-af54-a1aa17705306','0','删除业务表信息','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导入表结构',3,5,'module_generator:gencode:import',NULL,NULL,NULL,NULL,NULL,0,1,0,'导入表结构','null',0,28,124,'5a33aed1-8c8a-4d37-8b0d-f5490a63bb32','0','导入表结构','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量生成代码',3,6,'module_generator:gencode:operate',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量生成代码','null',0,28,125,'1768a26b-2ab5-4848-8d60-a279523ba948','0','批量生成代码','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('生成代码到指定路径',3,7,'module_generator:gencode:code',NULL,NULL,NULL,NULL,NULL,0,1,0,'生成代码到指定路径','null',0,28,126,'fe0e3fdb-2f21-4797-9924-8350a8108891','0','生成代码到指定路径','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询数据库表列表',3,8,'module_generator:dblist:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询数据库表列表','null',0,28,127,'b3a45d80-8c13-4b40-9dad-710f545f1cd5','0','查询数据库表列表','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('同步数据库',3,9,'module_generator:db:sync',NULL,NULL,NULL,NULL,NULL,0,1,0,'同步数据库','null',0,28,128,'4d314a4a-255e-4f69-8724-5570e7fb943f','0','同步数据库','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建插件',3,1,'module_application:portal:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建插件','null',0,29,129,'f0ce7748-fa4d-48a9-a533-5ddf826ce76f','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改插件',3,2,'module_application:portal:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改插件','null',0,29,130,'1bdd45a9-d6f5-442c-8305-c087e6e71236','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除插件',3,3,'module_application:portal:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除插件','null',0,29,131,'b08a1171-d2ee-4c9f-a93b-d32f3a602dbc','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改插件状态',3,4,'module_application:portal:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改应用状态','null',0,29,132,'4eeaf0a6-00cd-4a49-9edb-a0051e1c17bb','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情插件',3,5,'module_application:portal:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情插件','null',0,29,133,'0e257ce6-5b09-4cc3-a750-3b614c129fd5','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询插件',3,6,'module_application:portal:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询插件','null',0,29,134,'1dc1b753-86b9-4a4c-bbcc-3988dcae7c48','0','查询插件','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('AI对话',3,1,'module_ai:chat:ws',NULL,NULL,NULL,NULL,NULL,0,1,0,'AI对话','null',0,30,135,'1e91756a-ddff-4720-8220-f0206f23d96e','0','AI对话','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询会话',3,2,'module_ai:chat:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询会话','null',0,30,136,'dff41800-6a09-442d-a277-7c6b5bcb3543','0','查询会话','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('会话详情',3,3,'module_ai:chat:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'会话详情','null',0,30,137,'9db00448-c6c7-4997-9541-f15957dcf034','0','会话详情','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建会话',3,4,'module_ai:chat:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建会话','null',0,30,138,'65607884-3de0-4524-a9f7-bb4390260ea5','0','创建会话','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('更新会话',3,5,'module_ai:chat:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'更新会话','null',0,30,139,'1884493e-3cfe-4db7-bc50-1287177c9fc4','0','更新会话','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除会话',3,6,'module_ai:chat:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除会话','null',0,30,140,'d55ae6af-5b87-464f-a957-8f8bcc3109c2','0','删除会话','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询会话记忆',3,1,'module_ai:chat:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询会话记忆','null',0,31,141,'d8901c40-9cb2-412c-9de1-f868f3d87d52','0','查询会话记忆','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('会话记忆详情',3,2,'module_ai:chat:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'会话记忆详情','null',0,31,142,'231d07ac-4017-4c9a-b2fc-31ed00517b55','0','会话记忆详情','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除会话记忆',3,3,'module_ai:chat:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除会话记忆','null',0,31,143,'22965201-596e-480c-889c-713e9125f2b4','0','删除会话记忆','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('调度器监控',2,1,'module_task:cronjob:job:query','el-icon-DataLine','Job','/task/cronjob/job','module_task/cronjob/job/index',NULL,0,1,0,'调度器监控','null',0,32,144,'5d89d594-ce77-4604-8513-fd04a1796d51','0','调度器监控','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('节点管理',2,2,'module_task:cronjob:node:query','el-icon-Postcard','Node','/task/cronjob/node','module_task/cronjob/node/index',NULL,0,1,0,'节点管理','null',0,32,145,'3035f6b7-46cb-4adf-83f7-a8371a9a4c27','0','节点管理','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('流程编排',2,1,'module_task:workflow:definition:query','el-icon-SetUp','Workflow','/task/workflow/definition','module_task/workflow/definition/index',NULL,0,1,0,'流程编排','null',0,33,146,'d76b72be-830e-43c6-a46d-688b6971cbc8','0','Vue Flow 画布与发布执行','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('编排节点类型',2,2,'module_task:workflow:node-type:query','el-icon-Grid','WorkflowNodeType','/task/workflow/node-type','module_task/workflow/node-type/index',NULL,0,1,0,'编排节点类型','null',0,33,147,'c7ce03aa-aaef-4244-972c-d6152ea081fb','0','画布节点类型与 Prefect 执行逻辑','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建示例',3,1,'module_example:demo:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建示例','null',0,34,148,'b7b77d61-e7a2-48b7-a9cb-9e7abcc297b4','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('更新示例',3,2,'module_example:demo:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'更新示例','null',0,34,149,'c7f35f20-9209-4c45-88bb-e5905e22f6fb','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除示例',3,3,'module_example:demo:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除示例','null',0,34,150,'ddda2131-02d8-45a1-a312-e0c6db7279ca','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改示例状态',3,4,'module_example:demo:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改示例状态','null',0,34,151,'789b9206-ca70-4e9c-8f74-5430246a53d4','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导出示例',3,5,'module_example:demo:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'导出示例','null',0,34,152,'733b7a56-7108-4593-b19f-922c866d9dc0','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导入示例',3,6,'module_example:demo:import',NULL,NULL,NULL,NULL,NULL,0,1,0,'导入示例','null',0,34,153,'3af7d1bf-7bc4-4ff0-b9b8-6c349fffa096','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('下载导入示例模版',3,7,'module_example:demo:download',NULL,NULL,NULL,NULL,NULL,0,1,0,'下载导入示例模版','null',0,34,154,'39560624-d359-44d9-818b-fb5d83945cc4','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情示例',3,8,'module_example:demo:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情示例','null',0,34,155,'9a544f60-de48-46f2-a55e-8975c343a53b','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询示例',3,9,'module_example:demo:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询示例','null',0,34,156,'cd404bff-02d8-46ec-9f7a-59bd0ffe5d65','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('三级菜单',2,1,'module_example:demo01:query','menu','Demo01','/example/demo-group/demo01','module_example/demo01/index',NULL,0,1,0,'三级菜单','null',0,35,157,'04c3c837-735a-4cd3-b626-339df12d3cad','0','示例01管理','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询调度器',3,1,'module_task:cronjob:job:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询调度器','null',0,144,158,'5d69968d-51e6-4a9a-8e6f-1fc05f20fc28','0','查询调度器','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('控制调度器',3,2,'module_task:cronjob:job:scheduler',NULL,NULL,NULL,NULL,NULL,0,1,0,'控制调度器','null',0,144,159,'a57bf080-69c6-40b7-9780-3a4291895ee1','0','控制调度器','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('操作任务',3,3,'module_task:cronjob:job:task',NULL,NULL,NULL,NULL,NULL,0,1,0,'操作任务','null',0,144,160,'3709dd9d-a94a-4d9e-8fc8-7617ea4da92c','0','操作任务','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除执行日志',3,4,'module_task:cronjob:job:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除执行日志','null',0,144,161,'542e255e-4f6b-4304-b7fb-5ce0ccd0c328','0','删除执行日志','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情执行日志',3,5,'module_task:cronjob:job:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情执行日志','null',0,144,162,'7ba33ccf-2f30-4fe3-86d4-844356f102b4','0','详情执行日志','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建节点',3,1,'module_task:cronjob:node:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建节点','null',0,145,163,'20e8e9c8-37d4-45e9-ac1b-bf7cd66a1c6c','0','创建节点','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('调试节点',3,2,'module_task:cronjob:node:execute',NULL,NULL,NULL,NULL,NULL,0,1,0,'调试节点','null',0,145,164,'85a149d5-3f56-402d-820f-6c72d6b9f4f1','0','调试节点','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改节点',3,3,'module_task:cronjob:node:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改节点','null',0,145,165,'67b69ff3-24a9-479f-aa9a-4706451623bb','0','修改节点','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除节点',3,4,'module_task:cronjob:node:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除节点','null',0,145,166,'cbedc16d-9083-4eb3-ae4c-c09a52308f5c','0','删除节点','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情节点',3,5,'module_task:cronjob:node:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情节点','null',0,145,167,'7b8c7b09-0437-46c2-b1a2-a13ec86eed0a','0','详情节点','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询节点',3,6,'module_task:cronjob:node:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询节点','null',0,145,168,'02ddbcce-dcb6-4e27-9e0b-c175740dbe45','0','查询节点','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建流程',3,1,'module_task:workflow:definition:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建流程','null',0,146,169,'ddb5cc05-1b8c-43d4-a798-0b5094cc71ff','0','创建流程','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('执行流程',3,2,'module_task:workflow:definition:execute',NULL,NULL,NULL,NULL,NULL,0,1,0,'执行流程','null',0,146,170,'5f9ff974-8900-482b-9352-10914388a2d8','0','执行流程','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改流程',3,3,'module_task:workflow:definition:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改流程','null',0,146,171,'5e9f8760-22e6-4372-ab29-3098a977d198','0','修改流程','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除流程',3,4,'module_task:workflow:definition:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除流程','null',0,146,172,'367fe90b-78b8-41cf-96ad-1e8d2082bef3','0','删除流程','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情流程',3,5,'module_task:workflow:definition:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情流程','null',0,146,173,'022762b0-35c5-4245-8845-6a3c9d9959a7','0','详情流程','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询流程',3,6,'module_task:workflow:definition:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询流程','null',0,146,174,'3ffb663f-6883-4318-af0e-610f8b204bd4','0','查询流程','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建编排节点类型',3,1,'module_task:workflow:node-type:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建编排节点类型','null',0,147,175,'d1b152eb-30d4-4228-9fde-519edb30ff56','0','创建编排节点类型','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('修改编排节点类型',3,2,'module_task:workflow:node-type:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'修改编排节点类型','null',0,147,176,'7e05072c-7fd4-4312-9a9f-814568b7087e','0','修改编排节点类型','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除编排节点类型',3,3,'module_task:workflow:node-type:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除编排节点类型','null',0,147,177,'c87192a4-eb15-4364-8401-974d821d2def','0','删除编排节点类型','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情编排节点类型',3,4,'module_task:workflow:node-type:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情编排节点类型','null',0,147,178,'ca7eec7a-5f69-4857-8714-1236fb4256b5','0','详情编排节点类型','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询编排节点类型',3,5,'module_task:workflow:node-type:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询编排节点类型','null',0,147,179,'671c1eca-af1a-4c7d-b375-84b5bddd3ea3','0','查询编排节点类型','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('创建示例01',3,1,'module_example:demo01:create',NULL,NULL,NULL,NULL,NULL,0,1,0,'创建示例01','null',0,157,180,'1b5c66be-e455-420f-a467-68db516c9572','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('更新示例01',3,2,'module_example:demo01:update',NULL,NULL,NULL,NULL,NULL,0,1,0,'更新示例01','null',0,157,181,'eb8636cc-97ea-4cdd-80b6-72b371bb35d5','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('删除示例01',3,3,'module_example:demo01:delete',NULL,NULL,NULL,NULL,NULL,0,1,0,'删除示例01','null',0,157,182,'81b51b8d-ee68-4b84-992d-4696f47a5e3f','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('批量修改示例01状态',3,4,'module_example:demo01:patch',NULL,NULL,NULL,NULL,NULL,0,1,0,'批量修改示例01状态','null',0,157,183,'0df5a4f4-58b3-4eb9-bf12-fb2fd0d10340','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导出示例01',3,5,'module_example:demo01:export',NULL,NULL,NULL,NULL,NULL,0,1,0,'导出示例01','null',0,157,184,'30293680-f40e-4319-a563-8cd809a793e4','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('导入示例01',3,6,'module_example:demo01:import',NULL,NULL,NULL,NULL,NULL,0,1,0,'导入示例01','null',0,157,185,'4fa25498-dc11-4e70-96f3-ff6fcf2956fe','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('下载导入示例01模版',3,7,'module_example:demo01:download',NULL,NULL,NULL,NULL,NULL,0,1,0,'下载导入示例01模版','null',0,157,186,'d84e569f-27cc-426f-ad50-3ee6d997bb80','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('详情示例01',3,8,'module_example:demo01:detail',NULL,NULL,NULL,NULL,NULL,0,1,0,'详情示例01','null',0,157,187,'54d36424-1a55-4dfe-9b77-a6422ba7f376','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('查询示例01',3,9,'module_example:demo01:query',NULL,NULL,NULL,NULL,NULL,0,1,0,'查询示例01','null',0,157,188,'92ab3017-f621-46eb-ad1c-a8193b4247f6','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL);
/*!40000 ALTER TABLE `sys_menu` ENABLE KEYS */;

--
-- Table structure for table `sys_notice`
--

DROP TABLE IF EXISTS `sys_notice`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_notice` (
  `notice_title` varchar(64) NOT NULL COMMENT '公告标题',
  `notice_type` varchar(1) NOT NULL COMMENT '公告类型(1通知 2公告)',
  `notice_content` text COMMENT '公告内容',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_sys_notice_uuid` (`uuid`),
  KEY `ix_sys_notice_is_deleted` (`is_deleted`),
  KEY `ix_sys_notice_status` (`status`),
  KEY `ix_sys_notice_id` (`id`),
  KEY `ix_sys_notice_deleted_id` (`deleted_id`),
  KEY `ix_sys_notice_created_time` (`created_time`),
  KEY `ix_sys_notice_deleted_time` (`deleted_time`),
  KEY `ix_sys_notice_created_id` (`created_id`),
  KEY `ix_sys_notice_updated_id` (`updated_id`),
  KEY `ix_sys_notice_updated_time` (`updated_time`),
  CONSTRAINT `sys_notice_ibfk_1` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `sys_notice_ibfk_2` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `sys_notice_ibfk_3` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='通知公告表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_notice`
--

/*!40000 ALTER TABLE `sys_notice` DISABLE KEYS */;
/*!40000 ALTER TABLE `sys_notice` ENABLE KEYS */;

--
-- Table structure for table `sys_param`
--

DROP TABLE IF EXISTS `sys_param`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_param` (
  `config_name` varchar(64) NOT NULL COMMENT '参数名称',
  `config_key` varchar(500) NOT NULL COMMENT '参数键名',
  `config_value` varchar(500) DEFAULT NULL COMMENT '参数键值',
  `config_type` tinyint(1) DEFAULT NULL COMMENT '系统内置(True:是 False:否)',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_sys_param_uuid` (`uuid`),
  KEY `ix_sys_param_id` (`id`),
  KEY `ix_sys_param_updated_time` (`updated_time`),
  KEY `ix_sys_param_is_deleted` (`is_deleted`),
  KEY `ix_sys_param_status` (`status`),
  KEY `ix_sys_param_created_time` (`created_time`),
  KEY `ix_sys_param_deleted_time` (`deleted_time`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='系统参数表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_param`
--

/*!40000 ALTER TABLE `sys_param` DISABLE KEYS */;
INSERT INTO `sys_param` VALUES ('网站名称','sys_web_title','FastApiAdmin',1,1,'32d45f18-098a-40b1-b6a8-263075f194b2','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('网站描述','sys_web_description','FastApiAdmin 是完全开源的权限管理系统',1,2,'53f0a0d7-502a-4762-9b48-1ad1ae65f558','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('网页图标','sys_web_favicon','https://service.fastapiadmin.com/api/v1/static/image/favicon.png',1,3,'69c04e4d-7104-4ded-ad1f-02428e63a4c0','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('网站Logo','sys_web_logo','https://service.fastapiadmin.com/api/v1/static/image/logo.png',1,4,'a400e665-0f9e-4873-9f85-4ec85991af72','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('登录背景','sys_login_background','https://service.fastapiadmin.com/api/v1/static/image/background.svg',1,5,'3810d178-59fc-45d6-8b05-e36a3042098f','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('版权信息','sys_web_copyright','Copyright © 2025-2026 service.fastapiadmin.com 版权所有',1,6,'6d1968e2-caef-4057-a846-85c84b562fec','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('备案信息','sys_keep_record','陕ICP备2025069493号-1',1,7,'31b35782-f4ad-42e7-8f30-682b0720f2da','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('帮助文档','sys_help_doc','https://service.fastapiadmin.com',1,8,'a329d554-ba2a-4e63-b690-b79637d571fc','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('隐私政策','sys_web_privacy','https://github.com/fastapiadmin/FastapiAdmin/blob/master/LICENSE',1,9,'b72773c7-9a40-41a9-93ee-07385dc0ad2d','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('用户协议','sys_web_clause','https://github.com/fastapiadmin/FastapiAdmin/blob/master/LICENSE',1,10,'349dc9f0-8aa3-4a8c-b3f8-2422a94997f1','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('源码代码','sys_git_code','https://github.com/fastapiadmin/FastapiAdmin.git',1,11,'3b2fd418-c07c-4a48-b77e-3204379ad657','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('项目版本','sys_web_version','2.0.0',1,12,'3b9e9ab3-1b5f-4d9b-a20f-eed1f9f2463c','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('演示模式启用','demo_enable','false',1,13,'b5ad30cb-5d20-43a7-ba98-52c64262a236','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('演示访问IP白名单','ip_white_list','[\"127.0.0.1\"]',1,14,'b2eb0939-3140-4611-81e2-ec8a955942f4','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('接口白名单','white_api_list_path','[\"/api/v1/system/auth/login\", \"/api/v1/system/auth/token/refresh\", \"/api/v1/system/auth/captcha/get\", \"/api/v1/system/auth/logout\", \"/api/v1/system/config/info\", \"/api/v1/system/user/current/info\", \"/api/v1/system/notice/available\", \"/api/v1/system/auth/auto-login/users\", \"/api/v1/system/auth/auto-login/token\", \"/api/v1/system/auth/auto-login\"]',1,15,'bc38f010-bb80-4d27-ac2c-e7e43c273f90','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL),('访问IP黑名单','ip_black_list','[]',1,16,'4174af47-9685-42d5-aa99-80cbed552aaa','0','初始化数据','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL);
/*!40000 ALTER TABLE `sys_param` ENABLE KEYS */;

--
-- Table structure for table `sys_position`
--

DROP TABLE IF EXISTS `sys_position`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_position` (
  `name` varchar(64) NOT NULL COMMENT '岗位名称',
  `order` int NOT NULL COMMENT '显示排序',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_sys_position_uuid` (`uuid`),
  KEY `ix_sys_position_is_deleted` (`is_deleted`),
  KEY `ix_sys_position_status` (`status`),
  KEY `ix_sys_position_deleted_id` (`deleted_id`),
  KEY `ix_sys_position_created_time` (`created_time`),
  KEY `ix_sys_position_deleted_time` (`deleted_time`),
  KEY `ix_sys_position_id` (`id`),
  KEY `ix_sys_position_created_id` (`created_id`),
  KEY `ix_sys_position_updated_id` (`updated_id`),
  KEY `ix_sys_position_updated_time` (`updated_time`),
  CONSTRAINT `sys_position_ibfk_1` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `sys_position_ibfk_2` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `sys_position_ibfk_3` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='岗位表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_position`
--

/*!40000 ALTER TABLE `sys_position` DISABLE KEYS */;
/*!40000 ALTER TABLE `sys_position` ENABLE KEYS */;

--
-- Table structure for table `sys_role`
--

DROP TABLE IF EXISTS `sys_role`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_role` (
  `name` varchar(64) NOT NULL COMMENT '角色名称',
  `code` varchar(16) NOT NULL COMMENT '角色编码',
  `order` int NOT NULL COMMENT '显示排序',
  `data_scope` int NOT NULL COMMENT '数据权限范围(1:仅本人 2:本部门 3:本部门及以下 4:全部 5:自定义)',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  UNIQUE KEY `ix_sys_role_uuid` (`uuid`),
  KEY `ix_sys_role_updated_time` (`updated_time`),
  KEY `ix_sys_role_id` (`id`),
  KEY `ix_sys_role_is_deleted` (`is_deleted`),
  KEY `ix_sys_role_status` (`status`),
  KEY `ix_sys_role_created_time` (`created_time`),
  KEY `ix_sys_role_deleted_time` (`deleted_time`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_role`
--

/*!40000 ALTER TABLE `sys_role` DISABLE KEYS */;
INSERT INTO `sys_role` VALUES ('管理员角色','ADMIN',1,4,1,'3a16d455-8ab7-4ea7-8b17-3df9005c7941','0','初始化角色','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL);
/*!40000 ALTER TABLE `sys_role` ENABLE KEYS */;

--
-- Table structure for table `sys_role_depts`
--

DROP TABLE IF EXISTS `sys_role_depts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_role_depts` (
  `role_id` int NOT NULL COMMENT '角色ID',
  `dept_id` int NOT NULL COMMENT '部门ID',
  PRIMARY KEY (`role_id`,`dept_id`),
  KEY `dept_id` (`dept_id`),
  CONSTRAINT `sys_role_depts_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `sys_role` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `sys_role_depts_ibfk_2` FOREIGN KEY (`dept_id`) REFERENCES `sys_dept` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色部门关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_role_depts`
--

/*!40000 ALTER TABLE `sys_role_depts` DISABLE KEYS */;
/*!40000 ALTER TABLE `sys_role_depts` ENABLE KEYS */;

--
-- Table structure for table `sys_role_menus`
--

DROP TABLE IF EXISTS `sys_role_menus`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_role_menus` (
  `role_id` int NOT NULL COMMENT '角色ID',
  `menu_id` int NOT NULL COMMENT '菜单ID',
  PRIMARY KEY (`role_id`,`menu_id`),
  KEY `menu_id` (`menu_id`),
  CONSTRAINT `sys_role_menus_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `sys_role` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `sys_role_menus_ibfk_2` FOREIGN KEY (`menu_id`) REFERENCES `sys_menu` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='角色菜单关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_role_menus`
--

/*!40000 ALTER TABLE `sys_role_menus` DISABLE KEYS */;
/*!40000 ALTER TABLE `sys_role_menus` ENABLE KEYS */;

--
-- Table structure for table `sys_tenant`
--

DROP TABLE IF EXISTS `sys_tenant`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_tenant` (
  `name` varchar(100) NOT NULL COMMENT '租户名称',
  `code` varchar(100) NOT NULL COMMENT '租户编码',
  `start_time` datetime DEFAULT NULL COMMENT '开始时间',
  `end_time` datetime DEFAULT NULL COMMENT '结束时间',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  UNIQUE KEY `code` (`code`),
  UNIQUE KEY `ix_sys_tenant_uuid` (`uuid`),
  KEY `ix_sys_tenant_updated_time` (`updated_time`),
  KEY `ix_sys_tenant_is_deleted` (`is_deleted`),
  KEY `ix_sys_tenant_status` (`status`),
  KEY `ix_sys_tenant_created_time` (`created_time`),
  KEY `ix_sys_tenant_deleted_time` (`deleted_time`),
  KEY `ix_sys_tenant_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='租户表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_tenant`
--

/*!40000 ALTER TABLE `sys_tenant` DISABLE KEYS */;
INSERT INTO `sys_tenant` VALUES ('系统租户','system',NULL,NULL,1,'0d13262f-6547-402a-b1b3-65bc1d52e2b1','0','平台默认租户，id 固定为 1','2026-04-19 22:33:08','2026-04-19 22:33:08',0,NULL);
/*!40000 ALTER TABLE `sys_tenant` ENABLE KEYS */;

--
-- Table structure for table `sys_user`
--

DROP TABLE IF EXISTS `sys_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_user` (
  `username` varchar(64) NOT NULL COMMENT '用户名/登录账号',
  `password` varchar(255) NOT NULL COMMENT '密码哈希',
  `name` varchar(32) NOT NULL COMMENT '昵称',
  `mobile` varchar(11) DEFAULT NULL COMMENT '手机号',
  `email` varchar(64) DEFAULT NULL COMMENT '邮箱',
  `gender` varchar(1) DEFAULT NULL COMMENT '性别(0:男 1:女 2:未知)',
  `avatar` varchar(255) DEFAULT NULL COMMENT '头像URL地址',
  `is_superuser` tinyint(1) NOT NULL COMMENT '是否超管',
  `last_login` datetime DEFAULT NULL COMMENT '最后登录时间',
  `gitee_login` varchar(32) DEFAULT NULL COMMENT 'Gitee登录',
  `github_login` varchar(32) DEFAULT NULL COMMENT 'Github登录',
  `wx_login` varchar(32) DEFAULT NULL COMMENT '微信登录',
  `qq_login` varchar(32) DEFAULT NULL COMMENT 'QQ登录',
  `dept_id` int DEFAULT NULL COMMENT '部门ID',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `tenant_id` int NOT NULL COMMENT '租户ID',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `ix_sys_user_uuid` (`uuid`),
  UNIQUE KEY `mobile` (`mobile`),
  UNIQUE KEY `email` (`email`),
  KEY `ix_sys_user_deleted_id` (`deleted_id`),
  KEY `ix_sys_user_created_id` (`created_id`),
  KEY `ix_sys_user_id` (`id`),
  KEY `ix_sys_user_updated_time` (`updated_time`),
  KEY `ix_sys_user_dept_id` (`dept_id`),
  KEY `ix_sys_user_deleted_time` (`deleted_time`),
  KEY `ix_sys_user_updated_id` (`updated_id`),
  KEY `ix_sys_user_is_deleted` (`is_deleted`),
  KEY `ix_sys_user_status` (`status`),
  KEY `ix_sys_user_created_time` (`created_time`),
  KEY `ix_sys_user_tenant_id` (`tenant_id`),
  CONSTRAINT `sys_user_ibfk_1` FOREIGN KEY (`dept_id`) REFERENCES `sys_dept` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `sys_user_ibfk_2` FOREIGN KEY (`tenant_id`) REFERENCES `sys_tenant` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `sys_user_ibfk_3` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `sys_user_ibfk_4` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `sys_user_ibfk_5` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_user`
--

/*!40000 ALTER TABLE `sys_user` DISABLE KEYS */;
INSERT INTO `sys_user` VALUES ('admin','$2b$12$e2IJgS/cvHgJ0H3G7Xa08OXoXnk6N/NX3IZRtubBDElA0VLZhkNOa','超级管理员',NULL,NULL,'0','https://service.fastapiadmin.com/api/v1/static/image/avatar.png',1,NULL,NULL,NULL,NULL,NULL,1,1,'7ac2f530-b68e-4dc4-be6b-d6ed2a21c204','0','超级管理员','2026-04-19 22:33:09','2026-04-19 22:33:09',0,NULL,1,NULL,NULL,NULL);
/*!40000 ALTER TABLE `sys_user` ENABLE KEYS */;

--
-- Table structure for table `sys_user_positions`
--

DROP TABLE IF EXISTS `sys_user_positions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_user_positions` (
  `user_id` int NOT NULL COMMENT '用户ID',
  `position_id` int NOT NULL COMMENT '岗位ID',
  PRIMARY KEY (`user_id`,`position_id`),
  KEY `position_id` (`position_id`),
  CONSTRAINT `sys_user_positions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `sys_user_positions_ibfk_2` FOREIGN KEY (`position_id`) REFERENCES `sys_position` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户岗位关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_user_positions`
--

/*!40000 ALTER TABLE `sys_user_positions` DISABLE KEYS */;
/*!40000 ALTER TABLE `sys_user_positions` ENABLE KEYS */;

--
-- Table structure for table `sys_user_roles`
--

DROP TABLE IF EXISTS `sys_user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sys_user_roles` (
  `user_id` int NOT NULL COMMENT '用户ID',
  `role_id` int NOT NULL COMMENT '角色ID',
  PRIMARY KEY (`user_id`,`role_id`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `sys_user_roles_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `sys_user_roles_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `sys_role` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户角色关联表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sys_user_roles`
--

/*!40000 ALTER TABLE `sys_user_roles` DISABLE KEYS */;
INSERT INTO `sys_user_roles` VALUES (1,1);
/*!40000 ALTER TABLE `sys_user_roles` ENABLE KEYS */;

--
-- Table structure for table `task_job`
--

DROP TABLE IF EXISTS `task_job`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_job` (
  `job_id` varchar(64) NOT NULL COMMENT '任务ID',
  `job_name` varchar(128) DEFAULT NULL COMMENT '任务名称',
  `trigger_type` varchar(32) DEFAULT NULL COMMENT '触发方式: cron/interval/date/manual',
  `status` varchar(16) NOT NULL COMMENT '执行状态',
  `next_run_time` varchar(64) DEFAULT NULL COMMENT '下次执行时间',
  `job_state` text COMMENT '任务状态信息',
  `result` text COMMENT '执行结果',
  `error` text COMMENT '错误信息',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_task_job_uuid` (`uuid`),
  KEY `ix_task_job_updated_time` (`updated_time`),
  KEY `ix_task_job_is_deleted` (`is_deleted`),
  KEY `ix_task_job_created_time` (`created_time`),
  KEY `ix_task_job_deleted_time` (`deleted_time`),
  KEY `ix_task_job_job_id` (`job_id`),
  KEY `ix_task_job_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='任务执行日志表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_job`
--

/*!40000 ALTER TABLE `task_job` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_job` ENABLE KEYS */;

--
-- Table structure for table `task_node`
--

DROP TABLE IF EXISTS `task_node`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_node` (
  `name` varchar(64) NOT NULL COMMENT '节点名称',
  `code` varchar(32) NOT NULL COMMENT '节点编码',
  `jobstore` varchar(64) DEFAULT NULL COMMENT '存储器',
  `executor` varchar(64) DEFAULT NULL COMMENT '执行器',
  `trigger` varchar(64) DEFAULT NULL COMMENT '触发器',
  `trigger_args` text COMMENT '触发器参数',
  `func` text COMMENT '代码块',
  `args` text COMMENT '位置参数',
  `kwargs` text COMMENT '关键字参数',
  `coalesce` tinyint(1) DEFAULT NULL COMMENT '是否合并运行',
  `max_instances` int DEFAULT NULL COMMENT '最大实例数',
  `start_date` varchar(64) DEFAULT NULL COMMENT '开始时间',
  `end_date` varchar(64) DEFAULT NULL COMMENT '结束时间',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  UNIQUE KEY `ix_task_node_uuid` (`uuid`),
  KEY `ix_task_node_created_id` (`created_id`),
  KEY `ix_task_node_updated_id` (`updated_id`),
  KEY `ix_task_node_updated_time` (`updated_time`),
  KEY `ix_task_node_is_deleted` (`is_deleted`),
  KEY `ix_task_node_status` (`status`),
  KEY `ix_task_node_deleted_id` (`deleted_id`),
  KEY `ix_task_node_created_time` (`created_time`),
  KEY `ix_task_node_deleted_time` (`deleted_time`),
  KEY `ix_task_node_id` (`id`),
  CONSTRAINT `task_node_ibfk_1` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `task_node_ibfk_2` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `task_node_ibfk_3` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='节点类型表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_node`
--

/*!40000 ALTER TABLE `task_node` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_node` ENABLE KEYS */;

--
-- Table structure for table `task_workflow`
--

DROP TABLE IF EXISTS `task_workflow`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_workflow` (
  `name` varchar(128) NOT NULL COMMENT '流程名称',
  `code` varchar(64) NOT NULL COMMENT '流程编码',
  `workflow_status` varchar(32) NOT NULL COMMENT '流程状态: draft/published/archived',
  `nodes` json DEFAULT NULL COMMENT 'Vue Flow nodes JSON',
  `edges` json DEFAULT NULL COMMENT 'Vue Flow edges JSON',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_task_workflow_code` (`code`),
  UNIQUE KEY `ix_task_workflow_uuid` (`uuid`),
  KEY `ix_task_workflow_created_time` (`created_time`),
  KEY `ix_task_workflow_deleted_time` (`deleted_time`),
  KEY `ix_task_workflow_created_id` (`created_id`),
  KEY `ix_task_workflow_updated_id` (`updated_id`),
  KEY `ix_task_workflow_updated_time` (`updated_time`),
  KEY `ix_task_workflow_id` (`id`),
  KEY `ix_task_workflow_is_deleted` (`is_deleted`),
  KEY `ix_task_workflow_status` (`status`),
  KEY `ix_task_workflow_deleted_id` (`deleted_id`),
  CONSTRAINT `task_workflow_ibfk_1` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `task_workflow_ibfk_2` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `task_workflow_ibfk_3` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='工作流定义表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_workflow`
--

/*!40000 ALTER TABLE `task_workflow` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_workflow` ENABLE KEYS */;

--
-- Table structure for table `task_workflow_node_type`
--

DROP TABLE IF EXISTS `task_workflow_node_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_workflow_node_type` (
  `name` varchar(128) NOT NULL COMMENT '显示名称',
  `code` varchar(64) NOT NULL COMMENT '节点编码，对应画布 node.type',
  `category` varchar(32) NOT NULL COMMENT '分类: trigger/action/condition/control',
  `func` text NOT NULL COMMENT 'Python 代码块，须定义 handler(*args,**kwargs)',
  `args` text COMMENT '默认位置参数，逗号分隔',
  `kwargs` text COMMENT '默认关键字参数 JSON',
  `sort_order` int NOT NULL COMMENT '排序',
  `is_active` tinyint(1) NOT NULL COMMENT '是否启用',
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `uuid` varchar(64) NOT NULL COMMENT 'UUID全局唯一标识',
  `status` varchar(10) NOT NULL COMMENT '状态(0:正常 1:禁用)',
  `description` text COMMENT '备注/描述',
  `created_time` datetime NOT NULL COMMENT '创建时间',
  `updated_time` datetime NOT NULL COMMENT '更新时间',
  `is_deleted` tinyint(1) NOT NULL COMMENT '是否已删除(0:未删除 1:已删除)',
  `deleted_time` datetime DEFAULT NULL COMMENT '删除时间',
  `created_id` int DEFAULT NULL COMMENT '创建人ID',
  `updated_id` int DEFAULT NULL COMMENT '更新人ID',
  `deleted_id` int DEFAULT NULL COMMENT '删除人ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  UNIQUE KEY `ix_task_workflow_node_type_uuid` (`uuid`),
  KEY `ix_task_workflow_node_type_status` (`status`),
  KEY `ix_task_workflow_node_type_updated_id` (`updated_id`),
  KEY `ix_task_workflow_node_type_deleted_time` (`deleted_time`),
  KEY `ix_task_workflow_node_type_deleted_id` (`deleted_id`),
  KEY `ix_task_workflow_node_type_updated_time` (`updated_time`),
  KEY `ix_task_workflow_node_type_created_id` (`created_id`),
  KEY `ix_task_workflow_node_type_id` (`id`),
  KEY `ix_task_workflow_node_type_created_time` (`created_time`),
  KEY `ix_task_workflow_node_type_is_deleted` (`is_deleted`),
  CONSTRAINT `task_workflow_node_type_ibfk_1` FOREIGN KEY (`created_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `task_workflow_node_type_ibfk_2` FOREIGN KEY (`updated_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `task_workflow_node_type_ibfk_3` FOREIGN KEY (`deleted_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='工作流编排节点类型（非定时任务节点）';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_workflow_node_type`
--

/*!40000 ALTER TABLE `task_workflow_node_type` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_workflow_node_type` ENABLE KEYS */;

--
-- Dumping routines for database 'fastapiadmin'
--
--
-- WARNING: can't read the INFORMATION_SCHEMA.libraries table. It's most probably an old server 8.4.3.
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-04-19 22:34:05
