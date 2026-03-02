-- MySQL dump 10.13  Distrib 8.0.41, for Linux (x86_64)
--
-- Host: 127.0.0.1    Database: mjournee
-- ------------------------------------------------------
-- Server version	8.0.41-google

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
-- Current Database: `mjournee`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `mjournee` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `mjournee`;

--
-- Table structure for table `journal_entries`
--

DROP TABLE IF EXISTS `journal_entries`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `journal_entries` (
  `entry_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `patient_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `family_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `visit_date` date NOT NULL,
  `provider_name` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `visit_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `main_reason` text COLLATE utf8mb4_unicode_ci,
  `symptoms` text COLLATE utf8mb4_unicode_ci,
  `diagnoses` text COLLATE utf8mb4_unicode_ci,
  `treatments` text COLLATE utf8mb4_unicode_ci,
  `vital_signs` text COLLATE utf8mb4_unicode_ci,
  `test_results` text COLLATE utf8mb4_unicode_ci,
  `medications` text COLLATE utf8mb4_unicode_ci,
  `follow_up_instructions` text COLLATE utf8mb4_unicode_ci,
  `next_appointments` text COLLATE utf8mb4_unicode_ci,
  `action_items` text COLLATE utf8mb4_unicode_ci,
  `patient_questions` text COLLATE utf8mb4_unicode_ci,
  `family_concerns` text COLLATE utf8mb4_unicode_ci,
  `family_summary` text COLLATE utf8mb4_unicode_ci,
  `medical_terms_explained` text COLLATE utf8mb4_unicode_ci,
  `visit_summary` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `ai_confidence` decimal(4,3) DEFAULT NULL,
  `ai_model` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `processing_method` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `consent_given` tinyint(1) DEFAULT '1',
  `audio_deleted` tinyint(1) DEFAULT '1',
  `transcripts_deleted` tinyint(1) DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `personal_notes` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`entry_id`),
  KEY `session_id` (`session_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_family_id` (`family_id`),
  KEY `idx_visit_date` (`visit_date`),
  KEY `idx_patient_name` (`patient_name`),
  KEY `idx_created_at` (`created_at`),
  CONSTRAINT `journal_entries_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `live_sessions` (`session_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `journal_entries`
--

LOCK TABLES `journal_entries` WRITE;
/*!40000 ALTER TABLE `journal_entries` DISABLE KEYS */;
INSERT INTO `journal_entries` VALUES ('entry-44a06141-9aae-494e-8797-b7a8dd02e308','session-1759424120678','user-001','Mary Johnson','kris','2025-10-02','Healthcare Provider','medical visit','','[]','[]','[]','{}','[]','[]','[]','[]','[]','[]','[]','Medical visit completed.','{}','Medical visit on 2025-10-02 - medical visit. Medical visit completed.',0.500,'gpt-4','ai_medical_summarization',1,1,1,'2025-10-02 16:55:53','2025-10-02 16:55:53',NULL),('entry-812039d7-10e8-41a4-8b86-af0e66617f6b','session-37e0ff0c-3800-4e14-a65f-96dc71129e9c','user-001','Mary Johnson','kris','2025-10-01','Healthcare Provider','','','[]','[]','[]','{}','[]','[]','[]','[]','[]','[]','[]','Medical visit completed.','{}','Medical visit on 2025-10-01 - . Medical visit completed.',0.500,'gpt-4','ai_medical_summarization',1,1,1,'2025-10-01 23:23:47','2025-10-01 23:23:47',NULL),('entry-84741cbb-4ffe-4271-a190-0c0bae91ef37','session-1759439074953','user-001','Mary Johnson','kris','2025-10-01','Healthcare Provider','Medical VisitAI Generated','Not specified','Falling','DEXA Scan Required','None recorded','{\"note\": \"Not recorded\"}','[]','[]','None recorded','No appointments scheduled','[]','[]','[]','Medical visit completed.','{}','Medical visit on 2025-10-02 - . Medical visit completed.',0.500,'gpt-4','ai_medical_summarization',1,1,1,'2025-10-02 21:05:05','2025-10-03 14:40:16','DEXA Scan said osteoporosis'),('entry-e8e2f83c-15a8-4754-9fbb-88abbd657fa7','session-1759425468335','user-001','Mary Johnson','kris','2025-10-02','Healthcare Provider','medical visit','','[]','[]','[]','{}','[]','[]','[]','[]','[]','[]','[]','Medical visit completed.','{}','Medical visit on 2025-10-02 - medical visit. Medical visit completed.',0.500,'gpt-4','ai_medical_summarization',1,1,1,'2025-10-02 17:18:10','2025-10-02 17:18:10',NULL);
/*!40000 ALTER TABLE `journal_entries` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `live_sessions`
--

DROP TABLE IF EXISTS `live_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `live_sessions` (
  `session_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `patient_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `family_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_language` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'vi',
  `session_status` enum('active','completed','failed') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `started_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `ended_at` timestamp NULL DEFAULT NULL,
  `total_segments` int DEFAULT '0',
  `duration_seconds` int DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`session_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_family_id` (`family_id`),
  KEY `idx_status` (`session_status`),
  KEY `idx_started_at` (`started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `live_sessions`
--

LOCK TABLES `live_sessions` WRITE;
/*!40000 ALTER TABLE `live_sessions` DISABLE KEYS */;
INSERT INTO `live_sessions` VALUES ('session-1759424120678','user-001','Mary Johnson','kris','vi','active','2025-10-02 16:55:50',NULL,0,0,'2025-10-02 16:55:50','2025-10-02 16:55:50'),('session-1759425468335','user-001','Mary Johnson','kris','vi','active','2025-10-02 17:18:07',NULL,0,0,'2025-10-02 17:18:07','2025-10-02 17:18:07'),('session-1759439074953','user-001','Mary Johnson','kris','vi','active','2025-10-02 21:04:57',NULL,0,0,'2025-10-02 21:04:57','2025-10-02 21:04:57'),('session-37e0ff0c-3800-4e14-a65f-96dc71129e9c','user-001','Mary Johnson','kris','vi','completed','2025-10-01 23:21:51','2025-10-01 23:23:48',4,109,'2025-10-01 23:21:51','2025-10-01 23:23:48'),('session-3bf73a96-5c37-4c01-a1f6-b924cc37609f','user-001','Mary Johnson','kris','vi','completed','2025-10-01 23:06:28','2025-10-01 23:06:52',0,22,'2025-10-01 23:06:28','2025-10-01 23:06:52'),('session-4c443705-4727-4870-90e0-927ba9f80c1b','user-001','Mary Johnson','kris','vi','active','2025-10-01 23:12:16',NULL,0,0,'2025-10-01 23:12:16','2025-10-01 23:12:16'),('session-51fb8ff4-cfbb-4405-ad13-f0d72c95fea6','user-001','Mary Johnson','kris','vi','active','2025-10-02 16:18:17',NULL,0,0,'2025-10-02 16:18:17','2025-10-02 16:18:17'),('session-94f2dce4-92f1-4cd0-b456-4d6cc5e6202a','user-001','Mary Johnson','kris','vi','active','2025-10-01 23:12:24',NULL,0,0,'2025-10-01 23:12:24','2025-10-01 23:12:24'),('session-d5255236-619c-45ce-8e66-b6cc811fc47a','user-001','Mary Johnson','kris','vi','completed','2025-10-01 23:13:19','2025-10-01 23:13:52',0,32,'2025-10-01 23:13:19','2025-10-01 23:13:52');
/*!40000 ALTER TABLE `live_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `session_segments`
--

DROP TABLE IF EXISTS `session_segments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `session_segments` (
  `segment_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `session_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `speaker` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `speaker_role` enum('Healthcare Provider','Patient/Family','Unknown') COLLATE utf8mb4_unicode_ci DEFAULT 'Unknown',
  `original_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `translated_text` text COLLATE utf8mb4_unicode_ci,
  `timestamp_start` decimal(12,3) DEFAULT NULL,
  `timestamp_end` decimal(12,3) DEFAULT NULL,
  `confidence` decimal(4,3) DEFAULT NULL,
  `enrollment_match` tinyint(1) DEFAULT '0',
  `enrollment_confidence` decimal(4,3) DEFAULT NULL,
  `method` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`segment_id`),
  KEY `idx_session_id` (`session_id`),
  KEY `idx_speaker` (`speaker`),
  KEY `idx_created_at` (`created_at`),
  CONSTRAINT `session_segments_ibfk_1` FOREIGN KEY (`session_id`) REFERENCES `live_sessions` (`session_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `session_segments`
--

LOCK TABLES `session_segments` WRITE;
/*!40000 ALTER TABLE `session_segments` DISABLE KEYS */;
/*!40000 ALTER TABLE `session_segments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `voice_enrollments`
--

DROP TABLE IF EXISTS `voice_enrollments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `voice_enrollments` (
  `id` varchar(36) NOT NULL DEFAULT (uuid()),
  `family_id` varchar(255) NOT NULL,
  `speaker_name` varchar(255) NOT NULL,
  `relationship` varchar(100) NOT NULL,
  `encrypted_voice_profile` text NOT NULL,
  `quality_score` decimal(3,2) NOT NULL,
  `sample_count` int NOT NULL,
  `enrollment_date` timestamp NOT NULL,
  `active` tinyint(1) DEFAULT '1',
  `privacy_note` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `voice_enrollments`
--

LOCK TABLES `voice_enrollments` WRITE;
/*!40000 ALTER TABLE `voice_enrollments` DISABLE KEYS */;
INSERT INTO `voice_enrollments` VALUES ('048b9f6a-4bab-4ba6-9664-b317877514b2','kris','kris','family_member','gAAAAABozAUgQd-im_cLOxh8fmDHUquMoggPBHcxkvlBV7H9D_OZYvSsyK4lQa8wo0voarg-LR8_sZlkpwfU7up_MFENOAg65mrhcIlpREpqz_xEvofZGT8bFgB23ogWDdWuGw-e8cMA9u266pjblgKVFqNRjsYqOuWze2sSfpZ2Sg4swNCbKPc5S5gN4a3ETtvNVmvyjmphZB2Lu2cMLrFrZzBvoq9B_rqZSKtWsz6aFZ83GWXANnv-OhX1uKHlZcfRd7mTIynszbALsxyJ3HitaMOijERhcXH5cSZa0XeCD_BqF3Pza0wI9OYLbFtoMScm5Z9Ts8veQn3Veq2jKsZ-rIffkXGNqF2E101O-twYCqh5ODk2rOItH2c1BuwbjIfdNPQuzqOjdlSnWwxtHnHuRW-7WonzQp4lxSNejtBUNLvvtlY_DKdhO46W2ytRhbBfobhA9iewuKdkhIumwzE1RI364qXq8PfTtyrrKydYGp9MO-wSjG10x9LrbwdKonT2AHMIyaMpOHC3Odf6KsSdYs3Akd8pTQHaLFZ9hw_eCgEcxvXsW0N4Ck_nXbAGX7xjYiOYnimP-s8tUHhTfcwrBpaJ-EzTyTuMhOZAZUCXrD5QUemEQF34mwEYYLS7VxbocS0y0K7d0V6TA_JRiwlbJnB7-0CeXPPEU5UTnC35F4u9rrmTIZeHd4yjIEsr-lc2ygG5qdvn6wFVc8bPPg8wrFVluqwtoFs2unsE-yo9UNRNDcOlqHlGnWEKs5KTuinh2h9tslfz-JHowIeOmHjR75fHIR9Kbbjr8TjX0U1KVFCu0-rlv3rRdlpmAdxgPo1GuuSMPhoxtWW5CJMv-9F2kCeqJJXDHx25kuMJOjgBKMaaFrCkXUjqdZyWH7PuCHGhH7z7OsKkzIQNSmsx_JbDQbS5h5mIpyj74S52G9ckg2ZDTYFcqe4stsHmiXs_pRq9SCpbQ1V5q2GJGH9E1GKJAQGKNH8oNOCWbPjObgOD9TOVUkfQQdLh-zLs8aaW5fa_S85D_RRZiQnBjtkQdsh7EgkcxljDH5y8uB2VuuaeY1mGIda0x3emDzSjRBMQU0g1GtTPn7s9r6WkZpYOd0tRW9W4ICYFqrwn3Y_Z99VPcUEvVK-GvEMy-O_bTdhQMjbFTO0iqujyr1nZgn4z2cAw0zwF3o2UsBsLvBZdtxKQXqWCvA8mUIpZGYdsI4FqxXQpj78kaiwkXhaDTlKPydS2upaAP2owQyJbTDpG1lz5YeDsV8eHROtj7UN0WCkGD9npiFsg3MjH294BZGRxIfLOsyqax55xPlhCl2HVvr3g-lVk4MX09pFk8cMiNwQua-Gkorob-KqZ0dK0O4U1F_007kUOo4wqUhPJ0s8iQmTXjP0L1eHq6noQwUBDYFXo6sSea4NMJY26zwH_ecDhvayI7p6jxNJh9ojgs4WPX7D7F8K1uRMnsCu1HmW_dWXcdzYCHAFkrY8ZfIFPh7g8-GdW03y3Oc64oQbHZiCI3PR0AcCQBq6P1RjDJaHMHnDzkcEEUpn1nUkZm0uG6yqJu0w-vhjfz9NtL76SElcEDN6-z4TY-FZnQogtw_yRbEtnchb3xERbSNsGfyRY50SKxLuFT-cUV7JUcmB8wwSzJf9Wwe9wSAHvHbmScv7WG9apybTT-DMB8YxK6lAU0e0WZ1ZguLHFvXVNNmqIQ-JzIZUZ5-2Nst8an_0UHs7FXHe1AajhHSvYFWpVsr2JIikqqw8PPo-WYQdhyZM5xQ1kZKJh3DnOEdV5kgXtg5tQXPeAPmtBbWCq6QPzOKNKlEF5vdiL1gXU4bWt_DyYfI9-Mr_wi_aFXMnU-p8QFdONwXoU5snDgCug4410kJdsATZdoEpKEvsv5bhpYxAJE83hY7lGgS8H7tVCMiDgNO42B90QTeEhg4BHq-HTdAG-OdBMfzvEh99fLr4YlnLB_w5W9WkHUlMecl97aw7URQe4vop3nPdpeoRUXkLJNqI5bT029yQ3E4wLVMuZ3faIyS3XNqMIcNoRDcytHdWpM1A2qHPKOapr0otvyK_TkyUPwme30JmWdkEsqdtWwf6tMZar0vahfPo8CgLb2WFg0K9PNDxa8Q-MeyU58fDcebmLkKWBRJtNKXs9aOedLSRSeJVGQaFXk4GmheCnbkvRXT978rLkJ5_5EkDU0egrYGySNQnVaUI3lu4hnz_vUNBcBQSTi2yTCdpJZR1AAGy-7GxwL1e3pN-Zsateb6j1qVdPIE6NPk8vIz9m7KJ1jP8mQBfisFL6vd6JxrtvKAA=',1.00,14,'2025-09-18 09:12:01',1,'Voice profile stored as encrypted embeddings only - no raw audio retained','2025-09-18 13:12:01');
/*!40000 ALTER TABLE `voice_enrollments` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-11-21 18:37:40
